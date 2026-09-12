"""/chats: the chats the bot posts to — card, presets, test, refresh, stop; the chat picker.

Every `ch:` callback also works inside a group (`/setup → ⚙️ Configure here`): the chat
comes from the callback data, visibility is re-checked on each press, presets move only
the presser's accounts.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from bson import ObjectId
from bson.errors import InvalidId

from wklabs.lib.chats import (
    CHANNEL,
    LEFT,
    SUPERGROUP,
    VIA_PICKED,
    VIA_SETUP,
    Chat,
)
from wklabs.lib.delivery import PRESETS
from wklabs.lib.users import TgUser

from .. import texts
from ..callbacks import ChatCb, NavCb, RouteCb
from ..chat_inspect import inspect_chat
from ..context import AppContext
from ..keyboards import (
    PICK_CANCEL,
    PICK_CHANNEL,
    kb_back_chats,
    kb_pick_chat,
    kb_presets,
    kb_stop_confirm,
    kb_topics,
)
from .common import chat_card_screen, chats_screen, edit, in_group, visible_or_alert

log = logging.getLogger(__name__)
router = Router(name="chats")


# ------------------------------------------------------------------ list
@router.message(Command("chats"), F.chat.type == ChatType.PRIVATE)
async def cmd_chats(message: Message, ctx: AppContext, user: TgUser, state: FSMContext) -> None:
    await state.clear()
    text, kb = await chats_screen(ctx, user)
    await message.answer(text, reply_markup=kb)


@router.callback_query(NavCb.filter(F.screen == "chats"))
async def cb_chats(cb: CallbackQuery, ctx: AppContext, user: TgUser, state: FSMContext) -> None:
    await state.clear()
    text, kb = await chats_screen(ctx, user)
    await edit(cb, text, kb)


@router.message(CommandStart(deep_link=True, magic=F.args.startswith("chat_")))
async def cmd_start_chat(message: Message, ctx: AppContext, user: TgUser, bot: Bot) -> None:
    """`/start chat_<id>` from `/setup → ⚙️ In private` or the greeting: straight to the card."""
    try:
        chat_id = int((message.text or "").split("chat_", 1)[1])
    except (IndexError, ValueError):
        chat_id = 0
    from .common import visible_chat

    chat = await visible_chat(ctx, user, chat_id, bot=bot)
    if chat is None:
        text, kb = await chats_screen(ctx, user)
        await message.answer(text, reply_markup=kb)
        return
    text, kb = await chat_card_screen(ctx, user, chat, in_group=False)
    await message.answer(text, reply_markup=kb)


# ------------------------------------------------------------------ card
@router.callback_query(ChatCb.filter(F.action == "card"))
async def cb_card(
    cb: CallbackQuery, callback_data: ChatCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    chat = await visible_or_alert(ctx, cb, user, callback_data.chat, bot=bot)
    if chat is None:
        return
    text, kb = await chat_card_screen(ctx, user, chat, in_group=in_group(cb))
    await edit(cb, text, kb)


@router.callback_query(ChatCb.filter(F.action == "later"))
async def cb_later(cb: CallbackQuery) -> None:
    msg = cb.message
    if isinstance(msg, Message):
        await msg.edit_reply_markup(reply_markup=None)
    await cb.answer("ok — /chats whenever you want")


@router.callback_query(ChatCb.filter(F.action == "close"))
async def cb_close(cb: CallbackQuery) -> None:
    msg = cb.message
    if isinstance(msg, Message):
        try:
            await msg.delete()
        except Exception:
            await msg.edit_reply_markup(reply_markup=None)
    await cb.answer()


# --------------------------------------------------------------- presets
@router.callback_query(ChatCb.filter(F.action == "deliver"))
async def cb_deliver(
    cb: CallbackQuery, callback_data: ChatCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    chat = await visible_or_alert(ctx, cb, user, callback_data.chat, bot=bot)
    if chat is None:
        return
    if not await ctx.accounts.for_owner(user.id):
        await cb.answer("add a WaniKani account first: /accounts in private", show_alert=True)
        return
    if not chat.can_post:
        await cb.answer("I can't post there yet — see the hint on the card", show_alert=True)
        return
    await edit(cb, texts.presets_screen(chat), kb_presets(chat))


@router.callback_query(ChatCb.filter(F.action == "preset"))
async def cb_preset(
    cb: CallbackQuery, callback_data: ChatCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    chat = await visible_or_alert(ctx, cb, user, callback_data.chat, bot=bot)
    if chat is None:
        return
    preset = callback_data.arg if callback_data.arg in PRESETS else PRESETS[-1]
    accounts = await ctx.accounts.for_owner(user.id)
    accounts = [a for a in accounts if a.is_active or a.status == "paused"]
    if not accounts:
        await cb.answer("add a WaniKani account first: /accounts in private", show_alert=True)
        return
    if not chat.can_post:
        await cb.answer("I can't post there yet — see the hint on the card", show_alert=True)
        return
    if in_group(cb):
        await ctx.chats.add_member(chat.id, user.id, VIA_SETUP)
    try:
        res = await ctx.topics.apply_preset(chat, accounts, preset, by=user.id)
    except Exception as exc:
        log.exception("preset failed in %s", chat.id)
        await cb.answer(f"❌ {exc}"[:190], show_alert=True)
        return
    fresh = await ctx.chats.get(chat.id) or chat
    note = texts.preset_done(res.labels, res.created, res.reused, res.general)
    text, kb = await chat_card_screen(ctx, user, fresh, in_group=in_group(cb), note=note)
    await edit(cb, text, kb)


# ---------------------------------------------------- test / refresh / topics
@router.callback_query(ChatCb.filter(F.action == "test"))
async def cb_test(
    cb: CallbackQuery, callback_data: ChatCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    chat = await visible_or_alert(ctx, cb, user, callback_data.chat, bot=bot)
    if chat is None:
        return
    _, err = await ctx.notifier.send_one(chat.id, None, texts.test_message())
    if err is not None and not chat.is_private:
        insp = await inspect_chat(bot, chat.id)
        if insp is not None:
            await ctx.chats.apply_inspection(chat.id, insp)
        else:
            await ctx.chats.set_status(chat.id, LEFT)
        fresh = await ctx.chats.get(chat.id) or chat
        text, kb = await chat_card_screen(ctx, user, fresh, in_group=in_group(cb))
        await edit(cb, text, kb)
    await cb.answer(texts.test_result(err), show_alert=err is not None)


@router.callback_query(ChatCb.filter(F.action == "refresh"))
async def cb_refresh(
    cb: CallbackQuery, callback_data: ChatCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    chat = await visible_or_alert(ctx, cb, user, callback_data.chat, bot=bot)
    if chat is None:
        return
    if not chat.is_private:
        insp = await inspect_chat(bot, chat.id)
        if insp is not None:
            chat = await ctx.chats.apply_inspection(chat.id, insp)
        else:
            await ctx.chats.set_status(chat.id, LEFT)
            chat = await ctx.chats.get(chat.id) or chat
    text, kb = await chat_card_screen(ctx, user, chat, in_group=in_group(cb), note="🔄 checked")
    await edit(cb, text, kb)


@router.callback_query(ChatCb.filter(F.action == "topics"))
async def cb_topics(
    cb: CallbackQuery, callback_data: ChatCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    chat = await visible_or_alert(ctx, cb, user, callback_data.chat, bot=bot)
    if chat is None:
        return
    await edit(cb, texts.topics_list(chat), kb_topics(chat))


# ------------------------------------------------------- stop / forget
async def _my_routes_here(ctx: AppContext, user: TgUser, chat: Chat) -> tuple[list[str], list[str]]:
    mine = await ctx.accounts.for_owner(user.id)
    keys = [a.key for a in mine]
    here = {r.account for r in await ctx.routes.for_chat(chat.id) if r.account in keys}
    return [a.key for a in mine if a.key in here], [a.label for a in mine if a.key in here]


@router.callback_query(ChatCb.filter(F.action == "stop"))
async def cb_stop(
    cb: CallbackQuery, callback_data: ChatCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    chat = await visible_or_alert(ctx, cb, user, callback_data.chat, bot=bot)
    if chat is None:
        return
    keys, labels = await _my_routes_here(ctx, user, chat)
    if not keys:
        await cb.answer("nothing of yours goes here", show_alert=True)
        return
    await edit(cb, texts.stop_confirm(chat, labels), kb_stop_confirm(chat))


@router.callback_query(ChatCb.filter(F.action == "stop_yes"))
async def cb_stop_yes(
    cb: CallbackQuery, callback_data: ChatCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    chat = await visible_or_alert(ctx, cb, user, callback_data.chat, bot=bot)
    if chat is None:
        return
    keys, _ = await _my_routes_here(ctx, user, chat)
    n = await ctx.routes.disable_for_owner(chat.id, keys)
    for key in keys:  # never leave an account without delivery
        if not await ctx.routes.for_account(key):
            await ctx.chats.ensure_private(user.id)
            await ctx.routes.ensure_account_routes(key, user.id, created_by=user.id)
    text, kb = await chat_card_screen(
        ctx, user, chat, in_group=in_group(cb), note=texts.stopped(chat, n)
    )
    await edit(cb, text, kb)


@router.callback_query(ChatCb.filter(F.action == "forget"))
async def cb_forget(
    cb: CallbackQuery, callback_data: ChatCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    chat = await visible_or_alert(ctx, cb, user, callback_data.chat, bot=bot)
    if chat is None:
        return
    if chat.present:
        await cb.answer("I'm still in that chat — use 🚫 Stop here", show_alert=True)
        return
    await ctx.chats.forget(chat.id)
    await edit(cb, texts.forgotten(chat), kb_back_chats())


# ------------------------------------------------------------ pick a chat
@router.callback_query(NavCb.filter(F.screen == "addchat"))
async def cb_addchat(cb: CallbackQuery) -> None:
    msg = cb.message
    if isinstance(msg, Message) and msg.chat.type == ChatType.PRIVATE:
        await msg.answer(texts.pick_chat(), reply_markup=kb_pick_chat())
        await cb.answer()
    else:
        await cb.answer("open me in private for that", show_alert=True)


@router.message(F.chat_shared, F.chat.type == ChatType.PRIVATE)
async def msg_chat_shared(message: Message, ctx: AppContext, user: TgUser, bot: Bot) -> None:
    shared = message.chat_shared
    assert shared is not None
    chat_id = shared.chat_id
    title = getattr(shared, "title", None)
    await message.answer(texts.picked(title), reply_markup=ReplyKeyboardRemove())
    insp = await inspect_chat(bot, chat_id)
    if insp is None:
        kind = CHANNEL if shared.request_id == PICK_CHANNEL else SUPERGROUP
        await ctx.chats.seen(chat_id, type=kind, title=title, member=user.id, via=VIA_PICKED)
        await ctx.chats.set_status(chat_id, LEFT)
        await message.answer(texts.pick_absent(), reply_markup=kb_back_chats())
        return
    chat = await ctx.chats.apply_inspection(chat_id, insp, added_by=user.id)
    await ctx.chats.add_member(chat_id, user.id, VIA_PICKED)
    chat.member_ids.append(user.id)
    text, kb = await chat_card_screen(ctx, user, chat, in_group=False, note="✅ added")
    await message.answer(text, reply_markup=kb)


@router.message(F.text == PICK_CANCEL, F.chat.type == ChatType.PRIVATE)
async def msg_pick_cancel(message: Message) -> None:
    await message.answer(texts.pick_cancelled(), reply_markup=ReplyKeyboardRemove())


# ------------------------------------------------------------ route errors
@router.callback_query(RouteCb.filter(F.action == "recreate"))
async def cb_recreate(
    cb: CallbackQuery, callback_data: RouteCb, ctx: AppContext, user: TgUser
) -> None:
    try:
        route = await ctx.routes.get(ObjectId(callback_data.id))
    except InvalidId:
        route = None
    if route is None or route.account is None:
        await cb.answer("route not found", show_alert=True)
        return
    acc = await ctx.accounts.get(route.account)
    if acc is None or (acc.owner_tg_id != user.id and not user.is_admin):
        await cb.answer("not your account", show_alert=True)
        return
    if route.thread_id is not None:
        await cb.answer("already has a topic", show_alert=True)
        return
    try:
        topic = await ctx.topics.recreate(route)
    except Exception as exc:
        log.exception("recreate failed for route %s", route.id)
        await cb.answer(f"❌ {exc}"[:190], show_alert=True)
        return
    if topic is None:
        await cb.answer("can't create topics there — check my rights in /chats", show_alert=True)
        return
    await ctx.routes.clear_error(route.id)
    await edit(cb, texts.recreated(topic.name), kb_back_chats())
