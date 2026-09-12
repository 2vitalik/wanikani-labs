"""/setup in a group or forum: register + rights + one-tap presets; details via `ch:` screens."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message

from wklabs.lib.chats import VIA_SETUP
from wklabs.lib.users import TgUser

from .. import texts
from ..chat_inspect import inspect_chat
from ..context import AppContext
from ..keyboards import kb_setup_light

log = logging.getLogger(__name__)
router = Router(name="setup")
GROUPS = {ChatType.GROUP, ChatType.SUPERGROUP}


@router.message(Command("setup"), F.chat.type.in_(GROUPS))
async def cmd_setup(message: Message, ctx: AppContext, user: TgUser, bot: Bot) -> None:
    insp = await inspect_chat(bot, message.chat.id)
    if insp is not None:
        chat = await ctx.chats.apply_inspection(message.chat.id, insp)
    else:
        chat = await ctx.chats.seen(
            message.chat.id, type=str(message.chat.type), title=message.chat.title
        )
    await ctx.chats.add_member(chat.id, user.id, VIA_SETUP)
    accounts = await ctx.accounts.for_owner(user.id)
    await message.answer(
        texts.setup_light(chat, accounts=len(accounts)),
        reply_markup=kb_setup_light(
            chat, has_accounts=bool(accounts), bot_username=ctx.bot_username
        ),
    )
