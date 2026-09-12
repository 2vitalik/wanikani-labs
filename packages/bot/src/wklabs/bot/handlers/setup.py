"""/setup in a group or forum: which accounts are delivered here, layout, subjects/system."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    ChatMemberAdministrator,
    ChatMemberOwner,
    InlineKeyboardMarkup,
    Message,
)

from wklabs.lib.delivery import LAYOUT_SINGLE, LAYOUT_TOPICS, Chat
from wklabs.lib.users import TgUser

from .. import texts
from ..callbacks import Setup, SetupCb
from ..context import AppContext
from ..keyboards import SetupState, kb_setup
from .common import edit

log = logging.getLogger(__name__)
router = Router(name="setup")
GROUPS = {ChatType.GROUP, ChatType.SUPERGROUP}


async def _inspect_chat(message: Message, bot: Bot, user: TgUser, ctx: AppContext) -> Chat:
    member = await bot.get_chat_member(message.chat.id, bot.id)
    is_admin = isinstance(member, ChatMemberAdministrator | ChatMemberOwner)
    can_topics = isinstance(member, ChatMemberAdministrator) and bool(member.can_manage_topics)
    return await ctx.chats.upsert(
        message.chat.id,
        type=str(message.chat.type),
        title=message.chat.title,
        is_forum=bool(message.chat.is_forum),
        set_up_by=user.id,
        bot_is_admin=is_admin,
        can_manage_topics=can_topics,
    )


async def _initial_state(ctx: AppContext, user: TgUser, chat: Chat) -> SetupState:
    mine = {a.key for a in await ctx.accounts.for_owner(user.id)}
    st = SetupState()
    st.layout = (
        chat.layout
        if chat.layout == LAYOUT_TOPICS and chat.topics_possible
        else (
            LAYOUT_TOPICS
            if chat.topics_possible and not await ctx.routes.for_chat(chat.id)
            else LAYOUT_SINGLE
        )
    )
    for r in await ctx.routes.for_chat(chat.id):
        if r.account in mine:
            if r.account not in st.accounts:
                st.accounts.append(r.account)
        elif r.account is None and r.category == "subjects":
            st.subjects = True
        elif r.account is None and r.category == "system":
            st.system = True
    return st


async def _screen(
    ctx: AppContext, user: TgUser, chat: Chat, st: SetupState
) -> tuple[str, InlineKeyboardMarkup]:
    accounts = await ctx.accounts.for_owner(user.id)
    return texts.setup_screen(chat, st, mine=len(accounts)), kb_setup(
        st, accounts, chat, is_admin=user.is_admin
    )


@router.message(Command("setup"), F.chat.type.in_(GROUPS))
async def cmd_setup(
    message: Message, ctx: AppContext, user: TgUser, state: FSMContext, bot: Bot
) -> None:
    chat = await _inspect_chat(message, bot, user, ctx)
    st = await _initial_state(ctx, user, chat)
    await state.set_state(Setup.editing)
    await state.update_data(setup=st.to_dict())
    text, kb = await _screen(ctx, user, chat, st)
    await message.answer(text, reply_markup=kb)


@router.callback_query(SetupCb.filter(), Setup.editing)
async def cb_setup(
    cb: CallbackQuery, callback_data: SetupCb, ctx: AppContext, user: TgUser, state: FSMContext
) -> None:
    msg = cb.message
    if msg is None:
        await cb.answer()
        return
    chat = await ctx.chats.get(msg.chat.id)
    if chat is None:
        await cb.answer("run /setup again", show_alert=True)
        return
    st = SetupState.from_dict((await state.get_data()).get("setup"))
    f, v = callback_data.field, callback_data.value
    if f == "cancel":
        await state.clear()
        await edit(cb, texts.setup_cancelled())
        return
    if f == "apply":
        await state.clear()
        await edit(cb, *await apply_setup(ctx, user, chat, st))
        return
    if f == "acc":
        if v in st.accounts:
            st.accounts.remove(v)
        else:
            st.accounts.append(v)
    elif f == "layout" and v in (LAYOUT_TOPICS, LAYOUT_SINGLE):
        st.layout = v if chat.topics_possible else LAYOUT_SINGLE
    elif f == "subjects":
        st.subjects = not st.subjects
    elif f == "system" and user.is_admin:
        st.system = not st.system
    await state.update_data(setup=st.to_dict())
    await edit(cb, *await _screen(ctx, user, chat, st))


async def apply_setup(
    ctx: AppContext, user: TgUser, chat: Chat, st: SetupState
) -> tuple[str, None]:
    mine = await ctx.accounts.for_owner(user.id)
    labels: list[str] = []
    for acc in mine:
        if acc.key in st.accounts:
            await ctx.routes.move_account(acc.key, chat.id, created_by=user.id)
            labels.append(acc.label)
            continue
        for r in await ctx.routes.for_account(acc.key):
            if r.chat_id == chat.id:
                await ctx.routes.set_enabled(r.id, False)
        if not await ctx.routes.for_account(acc.key):  # never leave an account without delivery
            await ctx.chats.ensure_private(user.id)
            await ctx.routes.ensure_account_routes(acc.key, user.id, created_by=user.id)
    layout = st.layout if chat.topics_possible else LAYOUT_SINGLE
    chat = await ctx.chats.upsert(
        chat.id, type=chat.type, title=chat.title, is_forum=chat.is_forum, layout=layout
    )
    await ctx.routes.upsert(None, "subjects", chat.id, created_by=user.id, enabled=st.subjects)
    if user.is_admin:
        await ctx.routes.upsert(None, "system", chat.id, created_by=user.id, enabled=st.system)
    created = await ctx.topics.ensure_chat_topics(chat.id) if layout == LAYOUT_TOPICS else []
    log.info(
        "setup %s by %s: accounts=%s layout=%s topics=%s",
        chat.id,
        user.id,
        st.accounts,
        layout,
        created,
    )
    return texts.setup_done(chat, st, created, labels), None
