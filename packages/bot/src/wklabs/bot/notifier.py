"""Deliver pending events as digests along routes; idempotent via `events.notified_at`.

One event can travel several routes (shared chats, global categories);
`events.delivered` remembers which routes already got it, so a crash in the
middle does not resend.
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
from wklabs.lib.db import Db
from wklabs.lib.delivery import Route, RouteRepo
from wklabs.lib.subjects import load_subjects
from wklabs.lib.timeutil import utcnow
from wklabs.lib.users import TgUserRepo

from .digest import render
from .routing import target_for
from .topics import TopicManager

log = logging.getLogger(__name__)
Json = dict[str, Any]

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
PER_SEND_DELAY = 0.3


class Notifier:
    def __init__(
        self,
        db: Db,
        bot: Bot | None,
        *,
        routes: RouteRepo,
        accounts: AccountRepo,
        users: TgUserRepo,
        topics: TopicManager,
        tz: str,
    ) -> None:
        self.db = db
        self.bot = bot
        self.routes = routes
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
            texts = render(category, label, evs, subjects, self.tz)
            for route in routes:
                todo = [e for e in evs if route.id not in (e.get("delivered") or [])]
                if not todo:
                    continue
                msg_ids = await self.send_route(route, texts)
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
    async def send_route(self, route: Route, texts: list[str]) -> list[int]:
        thread = await self.topics.ensure_thread(route)
        return await self.send(route.chat_id, thread, texts, meta={"route": route.id})

    async def send(
        self,
        chat_id: int,
        thread_id: int | None,
        texts: list[str],
        *,
        meta: Json | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> list[int]:
        """Send texts to a chat/thread (or log them in dry-run). Returns message ids."""
        ids: list[int] = []
        if self.bot is None:
            for t in texts:
                log.info("[dry-run → %s/%s]\n%s", chat_id, thread_id, t)
            return ids
        for t in texts:
            for attempt in range(3):
                try:
                    msg = await self.bot.send_message(
                        chat_id,
                        t,
                        message_thread_id=thread_id,
                        link_preview_options=NO_PREVIEW,
                        reply_markup=reply_markup,
                    )
                    ids.append(msg.message_id)
                    await self.db.tg_messages.insert_one(
                        {
                            "chat_id": chat_id,
                            "thread_id": thread_id,
                            "message_id": msg.message_id,
                            "sent_at": utcnow(),
                            "chars": len(t),
                            **(meta or {}),
                        }
                    )
                    break
                except TelegramRetryAfter as exc:
                    log.warning("flood wait %ss", exc.retry_after)
                    await asyncio.sleep(exc.retry_after + 1)
                except TelegramForbiddenError as exc:
                    # user blocked the bot / bot kicked from the chat: stop delivering there
                    n = await self.routes.disable_chat(chat_id)
                    log.warning("chat %s forbidden (%s) → %d route(s) disabled", chat_id, exc, n)
                    return ids
                except TelegramBadRequest as exc:
                    if thread_id is not None and "thread" in str(exc).lower():
                        # topic deleted by hand → forget the thread, it is recreated next time
                        await self.db.tg_routes.update_many(
                            {"chat_id": chat_id, "thread_id": thread_id},
                            {"$set": {"thread_id": None, "thread_title": None}},
                        )
                        log.warning("thread %s/%s gone (%s) → cleared", chat_id, thread_id, exc)
                        return ids
                    log.exception(
                        "send to %s/%s failed (attempt %d)", chat_id, thread_id, attempt + 1
                    )
                    await asyncio.sleep(2 * (attempt + 1))
                except Exception:
                    log.exception(
                        "send to %s/%s failed (attempt %d)", chat_id, thread_id, attempt + 1
                    )
                    await asyncio.sleep(2 * (attempt + 1))
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
