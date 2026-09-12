"""Forum topics: presets create/find them in bulk, routes point at them, humans keep control.

The bot never creates a topic on delivery (a route without `thread_id` posts to
General), never recreates a deleted one silently, and renames only the topics it
created whose name nobody touched (T26 §3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from wklabs.lib.accounts import Account, AccountRepo
from wklabs.lib.chats import Chat, ChatRepo, Topic
from wklabs.lib.delivery import (
    BLUE,
    CATEGORY_COLOR,
    PRESET_GENERAL,
    PRESET_PER_CATEGORY,
    PURPLE,
    Route,
    RouteRepo,
    preset_topic_name,
)

log = logging.getLogger(__name__)


@dataclass(slots=True)
class PresetResult:
    labels: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    reused: int = 0
    general: bool = False


class TopicManager:
    def __init__(
        self, bot: Bot | None, chats: ChatRepo, routes: RouteRepo, accounts: AccountRepo
    ) -> None:
        self.bot = bot
        self.chats = chats
        self.routes = routes
        self.accounts = accounts

    async def ensure_thread(self, route: Route) -> int | None:
        """Where a route posts: its topic, or General/none. Never creates anything."""
        return route.thread_id

    async def create(self, chat_id: int, name: str, *, color: int = BLUE) -> Topic:
        assert self.bot is not None
        topic = await self.bot.create_forum_topic(chat_id, name=name, icon_color=color)
        await self.chats.remember_topic(chat_id, topic.message_thread_id, name, by_bot=True)
        log.info("created topic %r in %s -> thread %s", name, chat_id, topic.message_thread_id)
        return Topic(topic.message_thread_id, name, by_bot=True, bot_name=name)

    async def rename(self, chat_id: int, thread_id: int, name: str) -> bool:
        if self.bot is None:
            return False
        try:
            await self.bot.edit_forum_topic(chat_id, thread_id, name=name)
        except TelegramAPIError as exc:
            log.warning("could not rename topic %s/%s: %s", chat_id, thread_id, exc)
            return False
        await self.chats.remember_topic(chat_id, thread_id, name, by_bot=True)
        await self.routes.rename_thread(chat_id, thread_id, name)
        return True

    async def find_or_create(self, chat: Chat, name: str, color: int, res: PresetResult) -> Topic:
        found = chat.topic_by_name(name)
        if found is not None:
            res.reused += 1
            return found
        topic = await self.create(chat.id, name, color=color)
        chat.topics[topic.thread_id] = topic
        res.created.append(name)
        return topic

    async def apply_preset(
        self, chat: Chat, accounts: list[Account], preset: str, *, by: int
    ) -> PresetResult:
        """All categories of these accounts → this chat, topics per preset (T26 §1)."""
        res = PresetResult()
        can_topics = chat.is_forum and preset != PRESET_GENERAL and self.bot is not None
        for acc in accounts:
            res.labels.append(acc.label)
            for route in await self.routes.move_account(acc.key, chat.id, created_by=by):
                name = preset_topic_name(preset, route.category, acc.label) if can_topics else None
                if name is None:
                    await self.routes.set_thread(route.id, None, None, by=by)
                    res.general = True
                    continue
                existing = chat.topic_by_name(name)
                if existing is None and not chat.topics_possible:
                    await self.routes.set_thread(route.id, None, None, by=by)
                    res.general = True
                    continue
                color = (
                    CATEGORY_COLOR.get(route.category, BLUE)
                    if preset == PRESET_PER_CATEGORY
                    else PURPLE
                )
                topic = await self.find_or_create(chat, name, color, res)
                await self.routes.set_thread(route.id, topic.thread_id, topic.name, by=by)
        await self.chats.set_preset(chat.id, preset)
        log.info("preset %s in %s by %s: %s", preset, chat.id, by, res)
        return res

    async def recreate(self, route: Route) -> Topic | None:
        """After `topic deleted`: make the topic again under its last name and point back."""
        chat = await self.chats.get(route.chat_id)
        if chat is None or not chat.topics_possible or self.bot is None:
            return None
        name = route.thread_title or f"{route.icon} {route.category}"
        topic = await self.create(chat.id, name, color=CATEGORY_COLOR.get(route.category, BLUE))
        await self.routes.set_thread(route.id, topic.thread_id, topic.name)
        # sibling routes that lost the same topic (kept its title) come along
        for other in await self.routes.for_chat(chat.id, include_disabled=True):
            if other.id != route.id and other.thread_id is None and other.thread_title == name:
                await self.routes.set_thread(other.id, topic.thread_id, topic.name)
        return topic

    async def rename_account(self, account: str, old_label: str, new_label: str) -> int:
        """Account label changed → rename the bot's own untouched topics that carry it."""
        if self.bot is None or old_label == new_label:
            return 0
        n = 0
        done: set[tuple[int, int]] = set()
        for route in await self.routes.for_account(account, include_disabled=True):
            if route.thread_id is None or (route.chat_id, route.thread_id) in done:
                continue
            done.add((route.chat_id, route.thread_id))
            chat = await self.chats.get(route.chat_id)
            topic = chat.topic(route.thread_id) if chat else None
            if topic is None or not topic.by_bot or topic.name != topic.bot_name:
                continue
            if old_label not in topic.name:
                continue
            if await self.rename(
                route.chat_id, route.thread_id, topic.name.replace(old_label, new_label)
            ):
                n += 1
        return n
