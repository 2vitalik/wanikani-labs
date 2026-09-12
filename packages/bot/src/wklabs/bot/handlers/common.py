"""Shared helpers for handlers: safe edits, ownership checks, screens."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from wklabs.lib.accounts import PURGED, Account
from wklabs.lib.delivery import Chat, Route
from wklabs.lib.timeutil import utcnow
from wklabs.lib.users import TgUser

from .. import texts
from ..context import AppContext
from ..keyboards import kb_account_card, kb_accounts, kb_welcome

log = logging.getLogger(__name__)


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery, user: TgUser) -> bool:  # type: ignore[override]
        return user.is_admin


async def edit(cb: CallbackQuery, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    """Edit the screen under the pressed button (ignoring 'not modified')."""
    msg = cb.message
    if isinstance(msg, Message):
        try:
            await msg.edit_text(text, reply_markup=kb)
        except TelegramBadRequest as exc:
            if "not modified" not in str(exc):
                raise
    await cb.answer()


async def owned(ctx: AppContext, cb: CallbackQuery, user: TgUser, key: str) -> Account | None:
    acc = await ctx.accounts.get(key)
    if acc is None or acc.status == PURGED:
        await cb.answer("account not found", show_alert=True)
        return None
    if acc.owner_tg_id != user.id and not user.is_admin:  # unowned = admins only
        await cb.answer("not your account", show_alert=True)
        return None
    return acc


async def due_map(ctx: AppContext, accounts: list[Account]) -> dict[str, int]:
    keys = [a.key for a in accounts]
    out: dict[str, int] = {}
    async for s in ctx.db.current("summary").find({"_id": {"$in": keys}}, {"reviews_now": 1}):
        out[str(s["_id"])] = int(s.get("reviews_now") or 0)
    return out


async def accounts_screen(ctx: AppContext, user: TgUser) -> tuple[str, InlineKeyboardMarkup]:
    accounts = await ctx.accounts.for_owner(user.id)
    if not accounts:
        return texts.welcome_no_accounts(), kb_welcome()
    return texts.accounts_list(accounts), kb_accounts(accounts, await due_map(ctx, accounts))


async def routes_with_chats(
    ctx: AppContext, acc: Account, *, include_disabled: bool = False
) -> list[tuple[Route, Chat]]:
    out: list[tuple[Route, Chat]] = []
    cache: dict[int, Chat | None] = {}
    for r in await ctx.routes.for_account(acc.key, include_disabled=include_disabled):
        if r.chat_id not in cache:
            cache[r.chat_id] = await ctx.chats.get(r.chat_id)
        chat = cache[r.chat_id]
        if chat is None:
            chat = Chat(r.chat_id, "private", None, False, "single", None, False, False)
        out.append((r, chat))
    return out


async def last_sync_at(ctx: AppContext, key: str) -> datetime | None:
    st = await ctx.db.sync_state.find_one({"_id": f"{key}:assignments"}, {"last_ok_at": 1})
    return st.get("last_ok_at") if st else None


async def card_screen(ctx: AppContext, acc: Account) -> tuple[str, InlineKeyboardMarkup]:
    text = texts.account_card(
        acc,
        await routes_with_chats(ctx, acc),
        last_sync=await last_sync_at(ctx, acc.key),
        tz=ZoneInfo(ctx.settings.tz),
        now=utcnow(),
    )
    return text, kb_account_card(acc)


def chat_type(message: Message) -> str:
    return str(message.chat.type)


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
