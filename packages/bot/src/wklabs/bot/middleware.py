"""Every message/callback: upsert the Telegram user, gate blocked/pending, announce newcomers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from wklabs.lib.users import BLOCKED, PENDING

from . import texts
from .context import AppContext
from .keyboards import kb_new_user

log = logging.getLogger(__name__)


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
