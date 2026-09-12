"""Deliver pending events as digests along routes; idempotent via `events.notified_at`.

One event can travel several routes (shared chats, global categories);
`events.delivered` remembers which routes already got it, so a crash in the
middle does not resend. A failing route is marked (`status: error`) and its
owner told once; success clears the mark.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
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
from wklabs.lib.route_settings import effective
from wklabs.lib.subjects import load_subjects
from wklabs.lib.timeutil import utcnow
from wklabs.lib.users import TgUserRepo

from . import texts
from .digest import render
from .keyboards import kb_route_error
from .routing import target_for
from .topics import TopicManager

log = logging.getLogger(__name__)
Json = dict[str, Any]

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
PER_SEND_DELAY = 0.3


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
    ) -> None:
        self.db = db
        self.bot = bot
        self.routes = routes
        self.chats = chats
        self.accounts = accounts
        self.users = users
        self.topics = topics
        self.tz = ZoneInfo(tz)

    @property
    def dry_run(self) -> bool:
        return self.bot is None

    # ----------------------------------------------------------- events
    async def notify_pending(self, *, limit: int = 5000) -> int:
        """Send un-notified events grouped by (account, category) → routes; returns sent count."""
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
            account, category = target
            routes = await self.routes.for_target(account, category)
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
                    rendered[items] = render(category, label, evs, subjects, self.tz, items=items)
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

    # ------------------------------------------------------------- send
    async def send_route(
        self, route: Route, texts_: list[str], *, silent: bool = False
    ) -> list[int]:
        thread = await self.topics.ensure_thread(route)
        ids: list[int] = []
        for t in texts_:
            mid, err = await self.send_one(
                route.chat_id, thread, t, meta={"route": route.id}, silent=silent
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
