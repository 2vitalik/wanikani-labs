"""Forum topics: create once (bot must be admin with can_manage_topics), remember in Mongo."""

from __future__ import annotations

import logging

from aiogram import Bot

from wklabs.lib.db import Db
from wklabs.lib.timeutil import utcnow

from .routing import TopicDef, topic_defs

log = logging.getLogger(__name__)


class TopicManager:
    def __init__(self, db: Db, chat_id: int | None, accounts: list[str]) -> None:
        self.db = db
        self.chat_id = chat_id
        self.defs: dict[str, TopicDef] = {t.key: t for t in topic_defs(accounts)}
        self.threads: dict[str, int] = {}  # key -> message_thread_id

    async def load(self) -> None:
        async for d in self.db.tg_topics.find({"chat_id": self.chat_id}):
            self.threads[str(d["_id"])] = int(d["thread_id"])

    async def ensure(self, bot: Bot | None) -> list[str]:
        """Create missing topics; returns keys created. No-op without a bot (dry-run)."""
        await self.load()
        created: list[str] = []
        if bot is None or self.chat_id is None:
            return created
        for key, tdef in self.defs.items():
            if key in self.threads:
                continue
            topic = await bot.create_forum_topic(
                self.chat_id, name=tdef.title, icon_color=tdef.icon_color
            )
            self.threads[key] = topic.message_thread_id
            await self.db.tg_topics.replace_one(
                {"_id": key},
                {
                    "_id": key,
                    "chat_id": self.chat_id,
                    "thread_id": topic.message_thread_id,
                    "title": tdef.title,
                    "created_at": utcnow(),
                },
                upsert=True,
            )
            created.append(key)
            log.info("created forum topic %s -> thread %s", key, topic.message_thread_id)
        return created

    def thread_id(self, key: str) -> int | None:
        return self.threads.get(key)
