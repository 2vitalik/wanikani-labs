"""Forum topics for routes: created lazily on first delivery, renamed with the account label."""

from __future__ import annotations

import logging

from aiogram import Bot

from wklabs.lib.accounts import AccountRepo
from wklabs.lib.delivery import (
    BLUE,
    CATEGORY_COLOR,
    LAYOUT_TOPICS,
    ChatRepo,
    Route,
    RouteRepo,
    topic_title,
)

log = logging.getLogger(__name__)


class TopicManager:
    def __init__(
        self, bot: Bot | None, chats: ChatRepo, routes: RouteRepo, accounts: AccountRepo
    ) -> None:
        self.bot = bot
        self.chats = chats
        self.routes = routes
        self.accounts = accounts

    async def ensure_thread(self, route: Route) -> int | None:
        """Thread id for a route: None in private/single chats; forum topic created on demand."""
        if route.thread_id is not None:
            return route.thread_id
        chat = await self.chats.get(route.chat_id)
        if self.bot is None or chat is None or chat.layout != LAYOUT_TOPICS:
            return None
        label = None
        if route.account is not None:
            acc = await self.accounts.get(route.account)
            label = acc.label if acc else route.account
        title = topic_title(route.category, label)
        topic = await self.bot.create_forum_topic(
            chat.id, name=title, icon_color=CATEGORY_COLOR.get(route.category, BLUE)
        )
        await self.routes.set_thread(route.id, topic.message_thread_id, title)
        log.info(
            "created forum topic %r in %s -> thread %s", title, chat.id, topic.message_thread_id
        )
        return topic.message_thread_id

    async def ensure_chat_topics(self, chat_id: int) -> list[str]:
        """Create every missing topic for the enabled routes of a chat (after /setup)."""
        created: list[str] = []
        for route in await self.routes.for_chat(chat_id):
            if route.thread_id is None and await self.ensure_thread(route) is not None:
                fresh = await self.routes.get(route.id)
                created.append(fresh.thread_title or route.category if fresh else route.category)
        return created

    async def rename_account(self, account: str, label: str) -> int:
        """Account label changed → rename its topics (best effort)."""
        if self.bot is None:
            return 0
        n = 0
        for route in await self.routes.for_account(account, include_disabled=True):
            if route.thread_id is None:
                continue
            title = topic_title(route.category, label)
            if title == route.thread_title:
                continue
            try:
                await self.bot.edit_forum_topic(route.chat_id, route.thread_id, name=title)
            except Exception:
                log.warning("could not rename topic %s/%s", route.chat_id, route.thread_id)
                continue
            await self.routes.set_thread(route.id, route.thread_id, title)
            n += 1
        return n
