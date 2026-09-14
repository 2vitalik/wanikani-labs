"""Deliver notifications along routes: instant digests, session summaries (live + final).

Instant kinds (`live · milestones · subjects · system`) travel per event, idempotent
via `events.notified_at` / `events.delivered`. Sessions (T32 §7) run after every
sync per (account, gap): new instants extend or open sessions, a successful poll
past the gap closes them; a live message is *edited* in place (Telegram does not
notify on edits — zero noise) and finalized on close, tracked in `reports`.
A failing route is marked (`status: error`) and its owner told once.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup, LinkPreviewOptions

from wklabs.lib.accounts import AccountRepo
from wklabs.lib.chats import KICKED, ChatRepo
from wklabs.lib.db import Db
from wklabs.lib.delivery import (
    ERR_FORBIDDEN,
    ERR_NO_RIGHTS,
    ERR_TOPIC_CLOSED,
    ERR_TOPIC_DELETED,
    Route,
    RouteRepo,
)
from wklabs.lib.notify_settings import effective
from wklabs.lib.progress import (
    Matrix,
    current_level,
    due_count,
    reverse_apply,
    stage_matrix,
    subject_index,
)
from wklabs.lib.reports import ReportRepo, text_hash
from wklabs.lib.sessions import Session, SessionRepo
from wklabs.lib.stats import window_stats
from wklabs.lib.subjects import load_subjects
from wklabs.lib.timeutil import utcnow
from wklabs.lib.users import TgUserRepo

from . import texts
from .digest import render
from .keyboards import kb_route_error, kb_session
from .render.session import SessionView, render_session
from .routing import target_for
from .topics import TopicManager

log = logging.getLogger(__name__)
Json = dict[str, Any]

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
PER_SEND_DELAY = 0.3
SESSION_KIND = "session"


def classify_bad_request(exc: Exception) -> str | None:
    """Map a Telegram error to a route error code; None = transient, retry."""
    msg = str(exc).lower()
    if "topic_closed" in msg or "topic closed" in msg:
        return ERR_TOPIC_CLOSED
    if "thread not found" in msg or "topic_id_invalid" in msg or "message thread" in msg:
        return ERR_TOPIC_DELETED
    if "not enough rights" in msg or "have no rights" in msg or "write_forbidden" in msg:
        return ERR_NO_RIGHTS
    if "chat not found" in msg or "bot was kicked" in msg or "bot is not a member" in msg:
        return ERR_FORBIDDEN
    return None


class Notifier:
    def __init__(
        self,
        db: Db,
        bot: Bot | None,
        *,
        routes: RouteRepo,
        chats: ChatRepo,
        accounts: AccountRepo,
        users: TgUserRepo,
        topics: TopicManager,
        tz: str,
        sessions: SessionRepo | None = None,
        reports: ReportRepo | None = None,
    ) -> None:
        self.db = db
        self.bot = bot
        self.routes = routes
        self.chats = chats
        self.accounts = accounts
        self.users = users
        self.topics = topics
        self.tz = ZoneInfo(tz)
        self.sessions = sessions or SessionRepo(db)
        self.reports = reports or ReportRepo(db)

    @property
    def dry_run(self) -> bool:
        return self.bot is None

    # ----------------------------------------------------------- events
    async def notify_pending(self, *, limit: int = 5000) -> int:
        """Send un-notified events grouped by (account, kind) → routes; returns sent count."""
        pending: list[Json] = []
        async for ev in self.db.events.find({"notified_at": None}, sort=[("at", 1)], limit=limit):
            pending.append(ev)
        if not pending:
            return 0
        by_target: dict[tuple[str | None, str] | None, list[Json]] = defaultdict(list)
        for ev in pending:
            by_target[target_for(ev)].append(ev)
        now = utcnow()
        sent = 0
        silent = by_target.pop(None, [])
        if silent:
            await self._mark(silent, now, skipped=True)
        labels = await self.accounts.labels()
        for target, evs in by_target.items():
            assert target is not None
            account, kind = target
            routes = await self.routes.for_target(account, kind)
            if not routes:
                await self._mark(evs, now, skipped=True, no_route=True)
                continue
            subject_ids = {int(e["subject_id"]) for e in evs if e.get("subject_id") is not None}
            subjects = await load_subjects(self.db, subject_ids)
            label = labels.get(account, account) if account else None
            rendered: dict[str, list[str]] = {}
            for route in routes:
                todo = [e for e in evs if route.id not in (e.get("delivered") or [])]
                if not todo:
                    continue
                opts = effective(route)
                items = str(opts.get("items", "all"))
                if items not in rendered:
                    rendered[items] = render(kind, label, evs, subjects, self.tz, items=items)
                msg_ids = await self.send_route(
                    route, rendered[items], silent=bool(opts.get("silent"))
                )
                await self.db.events.update_many(
                    {"_id": {"$in": [e["_id"] for e in todo]}},
                    {
                        "$addToSet": {"delivered": route.id},
                        "$push": {"message_ids": {"$each": msg_ids}},
                    },
                )
                sent += len(msg_ids)
            await self._mark(evs, now)
        return sent

    async def _mark(self, evs: list[Json], now: Any, **flags: bool) -> None:
        await self.db.events.update_many(
            {"_id": {"$in": [e["_id"] for e in evs]}},
            {"$set": {"notified_at": now, "dry_run": self.dry_run, **flags}},
        )

    # --------------------------------------------------------- sessions
    async def notify_sessions(self, *, accounts: list[str] | None = None) -> int:
        """Session pass (T32 §7.2): ingest new instants, close idle, post/edit summaries."""
        by_account: dict[str, list[Route]] = defaultdict(list)
        for r in await self.routes.for_kind(SESSION_KIND):
            if r.account and (not accounts or r.account in accounts):
                by_account[r.account].append(r)
        sent = 0
        labels = await self.accounts.labels()
        for account, routes in by_account.items():
            acc = await self.accounts.get(account)
            if acc is None or not acc.is_active:
                continue
            by_gap: dict[int, list[Route]] = defaultdict(list)
            for r in routes:
                by_gap[int(effective(r)["gap"])].append(r)
            last_ok = await self.last_ok(account)
            now = utcnow()
            label = labels.get(account, account)
            for gap, group in by_gap.items():
                touched = {s.id for s in await self.sessions.ingest(account, gap, now=now)}
                closed = await self.sessions.close_idle(account, gap, last_ok, now=now)
                if closed is not None:
                    touched.add(closed.id)
                for s in await self.sessions.pending(account, gap):
                    sent += await self.deliver_session(s, group, label, final=True)
                    await self.sessions.mark_reported([s.id], now)
                cur = await self.sessions.current(account, gap)
                live = [r for r in group if effective(r)["live"]]
                if cur is not None and live and cur.id in touched:
                    sent += await self.deliver_session(cur, live, label, final=False)
        return sent

    async def last_ok(self, account: str) -> datetime | None:
        """The silence is proven only when both review sources polled fine (T32 §2)."""
        stamps: list[datetime] = []
        for res in ("review_statistics", "assignments"):
            st = await self.db.sync_state.find_one({"_id": f"{account}:{res}"}, {"last_ok_at": 1})
            ok = st.get("last_ok_at") if st else None
            if ok is None:
                return None
            stamps.append(ok)
        return min(stamps)

    async def build_view(
        self, session: Session, label: str, *, need_map: bool, live: bool, preview: bool = False
    ) -> SessionView:
        events = await self.sessions.events(session)
        ids = {int(e["subject_id"]) for e in events if e.get("subject_id") is not None}
        subjects = await load_subjects(self.db, ids)
        stats = window_stats(events, subjects)
        after: Matrix | None = None
        before: Matrix | None = None
        if need_map:
            index = await subject_index(self.db)
            after = await stage_matrix(self.db, session.account, index)
            before = reverse_apply(after, events, index)
        return SessionView(
            label=label,
            session=session,
            stats=stats,
            subjects=subjects,
            tz=self.tz,
            live=live,
            preview=preview,
            due=await due_count(self.db, session.account, utcnow()),
            level=await current_level(self.db, session.account),
            after=after,
            before=before,
        )

    async def deliver_session(
        self, session: Session, routes: list[Route], label: str, *, final: bool
    ) -> int:
        todo = [r for r in routes if not (final and r.id in session.delivered)]
        if not todo:
            return 0
        opts_by = {r.id: effective(r) for r in todo}
        need_map = any(o.get("changes") or o.get("map") for o in opts_by.values())
        view = await self.build_view(session, label, need_map=need_map, live=not final)
        if final:
            await self.sessions.set_stats(session.id, view.stats.to_doc())
        n_items = view.stats.n_items + len(view.stats.lessons)
        sent = 0
        for route in todo:
            opts = opts_by[route.id]
            existing = await self.reports.get(route.id, session.key)
            if final and n_items < int(opts.get("min_items", 1)) and existing is None:
                await self.sessions.mark_delivered(session.id, route.id)  # too small: no message
                continue
            texts_ = render_session(view, opts)
            kb = kb_session(session.id, live=not final)
            ids = await self.send_or_edit(
                route,
                session.key,
                texts_,
                final=final,
                silent=bool(opts.get("silent")),
                reply_markup=kb,
            )
            if final and (ids or self.dry_run):
                await self.sessions.mark_delivered(session.id, route.id)
            sent += len(ids)
        return sent

    async def preview_session(self, route: Route) -> str | None:
        """`📨 Preview`: the last closed session rendered with the route's current settings."""
        if route.account is None:
            return "not a session route"
        opts = effective(route)
        recent = await self.sessions.recent(route.account, int(opts["gap"]), limit=1)
        if not recent:
            return "no closed session yet for this gap"
        labels = await self.accounts.labels()
        view = await self.build_view(
            recent[0],
            labels.get(route.account, route.account),
            need_map=bool(opts.get("changes") or opts.get("map")),
            live=False,
            preview=True,
        )
        ids = await self.send_route(
            route,
            render_session(view, opts),
            silent=True,
            reply_markup=kb_session(recent[0].id, live=False),
        )
        return None if ids or self.dry_run else "send failed"

    # ------------------------------------------------------------- send
    async def send_or_edit(
        self,
        route: Route,
        key: str,
        texts_: list[str],
        *,
        final: bool,
        silent: bool = False,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> list[int]:
        """One report per (route, key): edit the earlier message when there is one."""
        h = text_hash(texts_)
        rep = await self.reports.get(route.id, key)
        if rep is not None and rep.message_id is not None and not rep.dry_run:
            if rep.text_hash == h and rep.final == final:
                return rep.message_ids
            if await self.edit_one(route.chat_id, rep.message_id, texts_[0], reply_markup):
                await self.reports.upsert(
                    route.id,
                    key,
                    chat_id=rep.chat_id,
                    thread_id=rep.thread_id,
                    message_ids=rep.message_ids,
                    final=final,
                    text_hash=h,
                )
                return rep.message_ids
        thread = await self.topics.ensure_thread(route)
        ids = await self.send_route(route, texts_, silent=silent, reply_markup=reply_markup)
        if ids or self.dry_run:
            await self.reports.upsert(
                route.id,
                key,
                chat_id=route.chat_id,
                thread_id=thread,
                message_ids=ids,
                final=final,
                text_hash=h,
                dry_run=self.dry_run,
            )
        return ids

    async def edit_one(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> bool:
        """Edit in place; False when the message is gone (→ send a new one)."""
        if self.bot is None:
            log.info("[dry-run edit → %s/%s]\n%s", chat_id, message_id, text)
            return True
        try:
            await self.bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=reply_markup,
                link_preview_options=NO_PREVIEW,
            )
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            return await self.edit_one(chat_id, message_id, text, reply_markup)
        except TelegramBadRequest as exc:
            if "not modified" in str(exc):
                return True
            log.warning("edit %s/%s failed: %s", chat_id, message_id, exc)
            return False
        except Exception:
            log.exception("edit %s/%s failed", chat_id, message_id)
            return False
        return True

    async def send_route(
        self,
        route: Route,
        texts_: list[str],
        *,
        silent: bool = False,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> list[int]:
        thread = await self.topics.ensure_thread(route)
        ids: list[int] = []
        for i, t in enumerate(texts_):
            last = i == len(texts_) - 1
            mid, err = await self.send_one(
                route.chat_id,
                thread,
                t,
                meta={"route": route.id},
                silent=silent,
                reply_markup=reply_markup if last else None,
            )
            if err is not None:
                await self._route_failed(route, err)
                return ids
            if mid is not None:
                ids.append(mid)
            await asyncio.sleep(PER_SEND_DELAY)
        if route.has_error and not self.dry_run:
            await self.routes.clear_error(route.id)
        return ids

    async def _route_failed(self, route: Route, err: str) -> None:
        chat = await self.chats.get(route.chat_id)
        chat_name = chat.name if chat else str(route.chat_id)
        if err == ERR_FORBIDDEN:
            n = await self.routes.disable_chat(route.chat_id)
            await self.chats.set_status(route.chat_id, KICKED)
            log.warning("chat %s forbidden → %d route(s) disabled", route.chat_id, n)
            await self._tell_owners_removed(route.chat_id, chat_name)
            return
        if err == ERR_TOPIC_DELETED and route.thread_id is not None:
            await self.routes.clear_thread(route.chat_id, route.thread_id)
            await self.chats.topic_gone(route.chat_id, route.thread_id)
        elif err == ERR_TOPIC_CLOSED and route.thread_id is not None:
            await self.chats.topic_closed(route.chat_id, route.thread_id)
        if not await self.routes.set_error(route.id, err):
            return  # same problem as before: the owner already knows
        fresh = await self.routes.get(route.id) or route
        label = None
        owner: int | None = None
        if route.account:
            acc = await self.accounts.get(route.account)
            if acc:
                label, owner = acc.label, acc.owner_tg_id
        text = texts.route_error(fresh, chat_name, label)
        if owner is not None:
            await self.send(owner, None, [text], reply_markup=kb_route_error(fresh))
        else:
            await self.admins(text)

    async def _tell_owners_removed(self, chat_id: int, chat_name: str) -> None:
        by_owner: dict[int, list[str]] = defaultdict(list)
        for r in await self.routes.for_chat(chat_id, include_disabled=True):
            if not r.account:
                continue
            acc = await self.accounts.get(r.account)
            if acc and acc.owner_tg_id is not None and acc.label not in by_owner[acc.owner_tg_id]:
                by_owner[acc.owner_tg_id].append(acc.label)
        for owner, labels in by_owner.items():
            await self.send(owner, None, [texts.removed_from_chat(chat_name, labels)])

    async def send_one(
        self,
        chat_id: int,
        thread_id: int | None,
        text: str,
        *,
        meta: Json | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
        silent: bool = False,
    ) -> tuple[int | None, str | None]:
        """One message → (message id, None) or (None, error code). Dry-run logs."""
        if self.bot is None:
            log.info("[dry-run → %s/%s]\n%s", chat_id, thread_id, text)
            return None, None
        for attempt in range(3):
            try:
                msg = await self.bot.send_message(
                    chat_id,
                    text,
                    message_thread_id=thread_id,
                    link_preview_options=NO_PREVIEW,
                    reply_markup=reply_markup,
                    disable_notification=silent or None,
                )
            except TelegramRetryAfter as exc:
                log.warning("flood wait %ss", exc.retry_after)
                await asyncio.sleep(exc.retry_after + 1)
                continue
            except TelegramForbiddenError as exc:
                log.warning("send to %s forbidden: %s", chat_id, exc)
                return None, ERR_FORBIDDEN
            except TelegramBadRequest as exc:
                code = classify_bad_request(exc)
                if code is not None:
                    log.warning("send to %s/%s: %s (%s)", chat_id, thread_id, code, exc)
                    return None, code
                log.exception("send to %s/%s failed (attempt %d)", chat_id, thread_id, attempt + 1)
                await asyncio.sleep(2 * (attempt + 1))
            except Exception:
                log.exception("send to %s/%s failed (attempt %d)", chat_id, thread_id, attempt + 1)
                await asyncio.sleep(2 * (attempt + 1))
            else:
                await self.db.tg_messages.insert_one(
                    {
                        "chat_id": chat_id,
                        "thread_id": thread_id,
                        "message_id": msg.message_id,
                        "sent_at": utcnow(),
                        "chars": len(text),
                        **(meta or {}),
                    }
                )
                return msg.message_id, None
        return None, "send failed"

    async def send(
        self,
        chat_id: int,
        thread_id: int | None,
        texts_: list[str],
        *,
        meta: Json | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> list[int]:
        """Send texts to a chat/thread (or log them in dry-run). Returns message ids."""
        ids: list[int] = []
        for t in texts_:
            mid, err = await self.send_one(
                chat_id, thread_id, t, meta=meta, reply_markup=reply_markup
            )
            if err is not None:
                return ids
            if mid is not None:
                ids.append(mid)
            await asyncio.sleep(PER_SEND_DELAY)
        return ids

    async def system(self, text: str, **meta: Any) -> list[int]:
        """`system` routes, or every admin's private chat when none is set up."""
        return await self.admins(f"🛠 {text}", meta=meta or None)

    async def admins(
        self,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        meta: Json | None = None,
    ) -> list[int]:
        routes = await self.routes.for_target(None, "system")
        ids: list[int] = []
        if routes:
            for route in routes:
                thread = await self.topics.ensure_thread(route)
                ids += await self.send(
                    route.chat_id, thread, [text], meta=meta, reply_markup=reply_markup
                )
            return ids
        for admin_id in await self.users.admin_ids_all():
            ids += await self.send(admin_id, None, [text], meta=meta, reply_markup=reply_markup)
        return ids


def html_code(text: str) -> str:
    return f"<code>{escape(text)}</code>"
