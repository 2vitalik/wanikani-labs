"""Outer middlewares: register the chat an update came from; upsert/gate the Telegram user."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Chat, Message, TelegramObject, User

from wklabs.lib.users import BLOCKED, PENDING

from . import texts
from .context import AppContext
from .keyboards import kb_new_user

log = logging.getLogger(__name__)

SEEN_TTL = 600  # s: re-touch `last_seen_at` at most this often per chat


def thread_of(message: Message) -> tuple[int, str | None] | None:
    """Topic a message came from, with its name when Telegram tells us."""
    if not message.message_thread_id or not message.is_topic_message:
        return None
    name = None
    if message.forum_topic_created is not None:
        name = message.forum_topic_created.name
    elif message.reply_to_message and message.reply_to_message.forum_topic_created:
        name = message.reply_to_message.forum_topic_created.name
    return message.message_thread_id, name


class ChatMiddleware(BaseMiddleware):
    """Any update: the chat, its author and the topic go to the registry.

    A private chat document doubles as "this user has talked to me in private",
    which is what decides whether the bot may DM them (greeting, route errors)."""

    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx
        self._cache: dict[int, tuple[tuple[Any, ...], float]] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat: Chat | None = data.get("event_chat")
        if chat is not None:
            try:
                await self._register(chat, data.get("event_from_user"), event)
            except Exception:
                log.exception("chat registry failed for %s", chat.id)
        return await handler(event, data)

    async def _register(self, chat: Chat, from_user: User | None, event: TelegramObject) -> None:
        thread = thread_of(event) if isinstance(event, Message) else None
        member = from_user.id if from_user is not None and not from_user.is_bot else None
        key = (chat.title, bool(chat.is_forum), member, thread)
        now = time.monotonic()
        last = self._cache.get(chat.id)
        if last is not None and last[0] == key and now - last[1] < SEEN_TTL:
            return
        self._cache[chat.id] = (key, now)
        await self.ctx.chats.seen(
            chat.id,
            type=str(chat.type),
            title=chat.title,
            is_forum=bool(chat.is_forum),
            member=member,
            thread=thread,
        )


class UserMiddleware(BaseMiddleware):
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user: User | None = data.get("event_from_user")
        if from_user is None or from_user.is_bot:
            return await handler(event, data)
        user, is_new = await self.ctx.users.ensure(
            from_user.id,
            username=from_user.username,
            first_name=from_user.first_name,
            lang=from_user.language_code,
        )
        data["user"] = user
        if is_new and not user.is_admin:
            log.info("new tg user %s (%s)", user.display, user.status)
            try:
                await self.ctx.notifier.admins(texts.new_user(user), reply_markup=kb_new_user(user))
            except Exception:
                log.exception("could not announce new user")
        if user.status == BLOCKED:
            log.info("ignored update from blocked user %s", user.id)
            return None
        if user.status == PENDING:
            if isinstance(event, Message) and event.chat.type == "private":
                await event.answer(texts.pending())
            elif isinstance(event, CallbackQuery):
                await event.answer(texts.pending(), show_alert=True)
            return None
        return await handler(event, data)
