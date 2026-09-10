"""Deliver pending events as per-topic digests; idempotent via `events.notified_at`."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import LinkPreviewOptions

from wklabs.lib.db import Db
from wklabs.lib.subjects import load_subjects
from wklabs.lib.timeutil import utcnow

from .digest import render_topic
from .routing import topic_for
from .topics import TopicManager

log = logging.getLogger(__name__)
Json = dict[str, Any]

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
PER_SEND_DELAY = 0.3


class Notifier:
    def __init__(
        self, db: Db, bot: Bot | None, topics: TopicManager, tz: str, chat_id: int | None
    ) -> None:
        self.db = db
        self.bot = bot
        self.topics = topics
        self.tz = ZoneInfo(tz)
        self.chat_id = chat_id

    @property
    def dry_run(self) -> bool:
        return self.bot is None or self.chat_id is None

    # ----------------------------------------------------------- events
    async def notify_pending(self, *, limit: int = 5000) -> int:
        """Send all un-notified events grouped by topic. Returns messages sent."""
        pending: list[Json] = []
        async for ev in self.db.events.find({"notified_at": None}, sort=[("at", 1)], limit=limit):
            pending.append(ev)
        if not pending:
            return 0
        by_topic: dict[str | None, list[Json]] = defaultdict(list)
        for ev in pending:
            by_topic[topic_for(ev)].append(ev)
        now = utcnow()
        sent = 0
        silent = by_topic.pop(None, [])
        if silent:
            await self.db.events.update_many(
                {"_id": {"$in": [e["_id"] for e in silent]}},
                {"$set": {"notified_at": now, "skipped": True}},
            )
        subject_ids = {
            int(e["subject_id"])
            for evs in by_topic.values()
            for e in evs
            if e.get("subject_id") is not None
        }
        subjects = await load_subjects(self.db, subject_ids)
        for key, evs in by_topic.items():
            assert key is not None
            texts = render_topic(key, evs, subjects, self.tz)
            ids = [e["_id"] for e in evs]
            msg_ids = await self.send(key, texts)
            await self.db.events.update_many(
                {"_id": {"$in": ids}},
                {"$set": {"notified_at": now, "message_ids": msg_ids, "dry_run": self.dry_run}},
            )
            sent += len(msg_ids)
        return sent

    # ------------------------------------------------------------- send
    async def send(
        self, topic_key: str, texts: list[str], *, meta: Json | None = None
    ) -> list[int]:
        """Send texts to a topic (or log them in dry-run). Returns message ids."""
        ids: list[int] = []
        if self.dry_run:
            for t in texts:
                log.info("[dry-run → %s]\n%s", topic_key, t)
            return ids
        assert self.bot is not None and self.chat_id is not None
        thread = self.topics.thread_id(topic_key)
        if thread is None:
            log.warning("no thread for topic %s — creating", topic_key)
            await self.topics.ensure(self.bot)
            thread = self.topics.thread_id(topic_key)
        for t in texts:
            for attempt in range(3):
                try:
                    msg = await self.bot.send_message(
                        self.chat_id, t, message_thread_id=thread, link_preview_options=NO_PREVIEW
                    )
                    ids.append(msg.message_id)
                    await self.db.tg_messages.insert_one(
                        {
                            "chat_id": self.chat_id,
                            "thread_id": thread,
                            "topic": topic_key,
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
                except Exception:
                    log.exception("send to %s failed (attempt %d)", topic_key, attempt + 1)
                    await asyncio.sleep(2 * (attempt + 1))
            await asyncio.sleep(PER_SEND_DELAY)
        return ids

    async def system(self, text: str, **meta: Any) -> list[int]:
        return await self.send("system", [f"🛠 {text}"], meta=meta or None)


def html_code(text: str) -> str:
    return f"<code>{escape(text)}</code>"
