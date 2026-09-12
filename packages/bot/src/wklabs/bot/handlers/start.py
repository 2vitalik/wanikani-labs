"""Public entry points: /start /ping /help /status; group fallbacks for private-only commands."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from wklabs.lib.users import TgUser

from .. import texts
from ..callbacks import NavCb
from ..context import AppContext
from ..keyboards import kb_back_accounts, kb_continue_private
from ..status_text import alive_text, status_text
from .common import accounts_screen, edit

router = Router(name="start")


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message, ctx: AppContext, user: TgUser) -> None:
    if not await ctx.accounts.for_owner(user.id) and not user.is_admin:
        seen = await ctx.db.tg_messages.count_documents({"chat_id": user.id}, limit=1)
        if not seen:
            await message.answer(texts.welcome_new(ctx.settings.access_policy, user.id))
    text, kb = await accounts_screen(ctx, user)
    await message.answer(text, reply_markup=kb)


@router.message(Command("ping"))
@router.message(CommandStart(), F.chat.type != ChatType.PRIVATE)
async def cmd_ping(message: Message, ctx: AppContext) -> None:
    uid = message.from_user.id if message.from_user else None
    await message.answer(await alive_text(ctx, uid, message.chat.id, message.message_thread_id))


@router.message(Command("help"), F.chat.type == ChatType.PRIVATE)
async def cmd_help(message: Message) -> None:
    await message.answer(texts.help_text(), reply_markup=kb_back_accounts())


@router.callback_query(NavCb.filter(F.screen == "help"))
async def cb_help(cb: CallbackQuery) -> None:
    await edit(cb, texts.help_text(), kb_back_accounts())


@router.message(Command("status"))
async def cmd_status(message: Message, ctx: AppContext, user: TgUser) -> None:
    accounts = (
        await ctx.accounts.list(status=None)
        if user.is_admin
        else await ctx.accounts.for_owner(user.id)
    )
    await message.answer(await status_text(ctx, accounts, admin=user.is_admin))


@router.message(Command("accounts", "help", "admin"), F.chat.type != ChatType.PRIVATE)
async def cmd_private_only(message: Message, ctx: AppContext) -> None:
    await message.answer(
        texts.continue_private(), reply_markup=kb_continue_private(ctx.bot_username)
    )
