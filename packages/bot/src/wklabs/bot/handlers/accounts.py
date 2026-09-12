"""/accounts (private): list → card → add · rename · replace token · pause · remove · delivery."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from bson import ObjectId
from bson.errors import InvalidId

from wklabs.lib.accounts import (
    ACTIVE,
    PAUSED,
    REMOVED,
    Account,
    InvalidTokenError,
    looks_like_token,
    validate_token,
)
from wklabs.lib.chats import Chat
from wklabs.lib.delivery import PRESET_GENERAL, PRESET_PER_CATEGORY, Route
from wklabs.lib.users import TgUser

from .. import texts
from ..callbacks import AccCb, AddAccount, NavCb, Rename, RouteCb
from ..context import AppContext
from ..keyboards import kb_back_accounts, kb_cancel, kb_delivery, kb_remove_confirm
from .common import (
    accounts_screen,
    as_int,
    card_screen,
    edit,
    owned,
    routes_with_chats,
    visible_chat,
)

log = logging.getLogger(__name__)
router = Router(name="accounts")
router.message.filter(F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)


# ------------------------------------------------------------------ screens
@router.message(Command("accounts"))
async def cmd_accounts(message: Message, ctx: AppContext, user: TgUser, state: FSMContext) -> None:
    await state.clear()
    text, kb = await accounts_screen(ctx, user)
    await message.answer(text, reply_markup=kb)


@router.callback_query(NavCb.filter(F.screen.in_({"accounts", "cancel"})))
async def cb_accounts(cb: CallbackQuery, ctx: AppContext, user: TgUser, state: FSMContext) -> None:
    await state.clear()
    text, kb = await accounts_screen(ctx, user)
    await edit(cb, text, kb)


@router.callback_query(AccCb.filter(F.action == "card"))
async def cb_card(
    cb: CallbackQuery, callback_data: AccCb, ctx: AppContext, user: TgUser, state: FSMContext
) -> None:
    acc = await owned(ctx, cb, user, callback_data.key)
    if acc is None:
        return
    await state.clear()
    text, kb = await card_screen(ctx, acc)
    await edit(cb, text, kb)


# ---------------------------------------------------------------- add token
@router.callback_query(NavCb.filter(F.screen == "add"))
async def cb_add(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddAccount.token)
    await state.update_data(replace="")
    await edit(cb, texts.add_prompt(), kb_cancel())


@router.callback_query(AccCb.filter(F.action == "token"))
async def cb_token(
    cb: CallbackQuery, callback_data: AccCb, ctx: AppContext, user: TgUser, state: FSMContext
) -> None:
    acc = await owned(ctx, cb, user, callback_data.key)
    if acc is None:
        return
    await state.set_state(AddAccount.token)
    await state.update_data(replace=acc.key)
    await edit(cb, texts.add_prompt(acc), kb_cancel())


@router.message(AddAccount.token, F.text)
async def msg_token(message: Message, ctx: AppContext, user: TgUser, state: FSMContext) -> None:
    data = await state.get_data()
    await process_token(
        message, ctx, user, state, replace_key=str(data.get("replace") or "") or None
    )


@router.message(StateFilter(None), F.text.func(looks_like_token))
async def msg_token_anywhere(
    message: Message, ctx: AppContext, user: TgUser, state: FSMContext
) -> None:
    """A token pasted outside the dialog (e.g. after a restart) is still handled — and deleted."""
    await process_token(message, ctx, user, state, replace_key=None)


async def process_token(
    message: Message, ctx: AppContext, user: TgUser, state: FSMContext, *, replace_key: str | None
) -> None:
    text = (message.text or "").strip()
    try:
        await message.delete()
    except Exception:
        log.warning("could not delete the token message in chat %s", message.chat.id)
    if not looks_like_token(text):
        await message.answer(texts.not_a_token(), reply_markup=kb_cancel())
        return
    try:
        ident = await validate_token(text)
    except InvalidTokenError:
        await message.answer(texts.token_rejected(), reply_markup=kb_cancel())
        return
    except Exception as exc:
        log.exception("token validation failed")
        await message.answer(texts.token_error(exc), reply_markup=kb_cancel())
        return
    await state.clear()
    existing = await ctx.accounts.by_wk_id(ident.wk_id)
    if replace_key and (existing is None or existing.key != replace_key):
        expected = await ctx.accounts.get(replace_key)
        if expected is not None:
            await message.answer(
                texts.token_other_user(ident, expected), reply_markup=kb_back_accounts()
            )
            return
    if existing is None:
        acc = await ctx.accounts.create(ident, text, owner_tg_id=user.id, source="bot")
        await ctx.chats.ensure_private(user.id)
        await ctx.routes.ensure_account_routes(acc.key, user.id, created_by=user.id)
        note = await message.answer(texts.added_syncing(acc, ident))
        res = await ctx.run_sync(accounts=[acc.key])
        await note.edit_text(
            texts.added_done(acc, ident, res, private=True), reply_markup=kb_back_accounts()
        )
        return
    if existing.owner_tg_id not in (None, user.id) and not user.is_admin:
        await message.answer(texts.token_foreign(), reply_markup=kb_back_accounts())
        await ctx.notifier.admins(texts.admin_foreign_token(user, existing))
        return
    was = existing.status
    acc = await ctx.accounts.set_token(existing.key, ident, text)
    if existing.owner_tg_id is None:
        await ctx.accounts.set_owner(acc.key, user.id)
    if was == REMOVED:
        await ctx.routes.resume_account(acc.key)
        if not await ctx.routes.for_account(acc.key):
            await ctx.chats.ensure_private(user.id)
            await ctx.routes.ensure_account_routes(acc.key, user.id, created_by=user.id)
    await message.answer(texts.token_replaced(acc, was), reply_markup=kb_back_accounts())


# ------------------------------------------------------------------- rename
@router.callback_query(AccCb.filter(F.action == "rename"))
async def cb_rename(
    cb: CallbackQuery, callback_data: AccCb, ctx: AppContext, user: TgUser, state: FSMContext
) -> None:
    acc = await owned(ctx, cb, user, callback_data.key)
    if acc is None:
        return
    await state.set_state(Rename.label)
    await state.update_data(key=acc.key)
    await edit(cb, texts.rename_prompt(acc), kb_cancel())


@router.message(Rename.label, F.text)
async def msg_rename(message: Message, ctx: AppContext, user: TgUser, state: FSMContext) -> None:
    key = str((await state.get_data()).get("key") or "")
    acc = await ctx.accounts.get(key)
    if acc is None or (acc.owner_tg_id != user.id and not user.is_admin):
        await state.clear()
        return
    label = (message.text or "").strip()
    if not 1 <= len(label) <= 32:
        await message.answer(texts.rename_bad(), reply_markup=kb_cancel())
        return
    await ctx.accounts.set_label(acc.key, label)
    await ctx.topics.rename_account(acc.key, acc.label, label)
    await state.clear()
    fresh = await ctx.accounts.get(acc.key)
    assert fresh is not None
    text, kb = await card_screen(ctx, fresh)
    await message.answer(text, reply_markup=kb)


# ------------------------------------------------------- pause / remove
@router.callback_query(AccCb.filter(F.action.in_({"pause", "resume"})))
async def cb_pause(cb: CallbackQuery, callback_data: AccCb, ctx: AppContext, user: TgUser) -> None:
    acc = await owned(ctx, cb, user, callback_data.key)
    if acc is None:
        return
    if callback_data.action == "pause" and acc.status == ACTIVE:
        await ctx.accounts.set_status(acc.key, PAUSED, "paused by owner")
    elif callback_data.action == "resume" and acc.status == PAUSED:
        await ctx.accounts.set_status(acc.key, ACTIVE)
    fresh = await ctx.accounts.get(acc.key)
    assert fresh is not None
    text, kb = await card_screen(ctx, fresh)
    await edit(cb, text, kb)


@router.callback_query(AccCb.filter(F.action == "remove"))
async def cb_remove(cb: CallbackQuery, callback_data: AccCb, ctx: AppContext, user: TgUser) -> None:
    acc = await owned(ctx, cb, user, callback_data.key)
    if acc is None:
        return
    await edit(cb, texts.remove_confirm(acc), kb_remove_confirm(acc))


@router.callback_query(AccCb.filter(F.action == "remove_yes"))
async def cb_remove_yes(
    cb: CallbackQuery, callback_data: AccCb, ctx: AppContext, user: TgUser
) -> None:
    acc = await owned(ctx, cb, user, callback_data.key)
    if acc is None:
        return
    await ctx.accounts.remove(acc.key)
    await ctx.routes.suspend_account(acc.key)
    await edit(cb, texts.removed(acc), kb_back_accounts())


# ----------------------------------------------------------------- delivery
async def delivery_screen(ctx: AppContext, acc: Account) -> tuple[str, InlineKeyboardMarkup]:
    all_routes = await routes_with_chats(ctx, acc, include_disabled=True)
    chat_ids = sorted({c.id for r, c in all_routes if r.enabled})
    if not chat_ids and acc.owner_tg_id is not None:
        chat_ids = [acc.owner_tg_id]
    rows = [(r, c) for r, c in all_routes if c.id in chat_ids]
    subjects: list[tuple[Chat, Route | None]] = []
    for cid in chat_ids:
        chat = await ctx.chats.get(cid)
        if chat is None:
            chat = await ctx.chats.ensure_private(cid)
        found = [
            r
            for r in await ctx.routes.for_chat(cid, include_disabled=True)
            if r.account is None and r.category == "subjects"
        ]
        subjects.append((chat, found[0] if found else None))
    owner_chats = await ctx.chats.visible_to(acc.owner_tg_id) if acc.owner_tg_id else []
    move_to = [c for c in owner_chats if c.id not in chat_ids and c.present and c.can_post]
    return texts.delivery(acc, rows), kb_delivery(acc, rows, subjects, move_to)


@router.callback_query(AccCb.filter(F.action == "delivery"))
async def cb_delivery(
    cb: CallbackQuery, callback_data: AccCb, ctx: AppContext, user: TgUser
) -> None:
    acc = await owned(ctx, cb, user, callback_data.key)
    if acc is None:
        return
    text, kb = await delivery_screen(ctx, acc)
    await edit(cb, text, kb)


@router.callback_query(RouteCb.filter())
async def cb_route_toggle(
    cb: CallbackQuery, callback_data: RouteCb, ctx: AppContext, user: TgUser
) -> None:
    try:
        route = await ctx.routes.get(ObjectId(callback_data.id))
    except InvalidId:
        route = None
    if route is None or route.account is None:
        await cb.answer("route not found", show_alert=True)
        return
    acc = await owned(ctx, cb, user, route.account)
    if acc is None:
        return
    await ctx.routes.set_enabled(route.id, not route.enabled)
    text, kb = await delivery_screen(ctx, acc)
    await edit(cb, text, kb)


async def _user_chat(ctx: AppContext, user: TgUser, chat_id: int) -> Chat | None:
    return await visible_chat(ctx, user, chat_id)


@router.callback_query(AccCb.filter(F.action == "subj"))
async def cb_subjects_toggle(
    cb: CallbackQuery, callback_data: AccCb, ctx: AppContext, user: TgUser
) -> None:
    acc = await owned(ctx, cb, user, callback_data.key)
    if acc is None:
        return
    chat = await _user_chat(ctx, user, as_int(callback_data.arg))
    if chat is None:
        await cb.answer("not your chat", show_alert=True)
        return
    current = [
        r
        for r in await ctx.routes.for_chat(chat.id, include_disabled=True)
        if r.account is None and r.category == "subjects"
    ]
    enabled = not (current and current[0].enabled)
    await ctx.routes.upsert(None, "subjects", chat.id, created_by=user.id, enabled=enabled)
    text, kb = await delivery_screen(ctx, acc)
    await edit(cb, text, kb)


@router.callback_query(AccCb.filter(F.action == "move"))
async def cb_move(cb: CallbackQuery, callback_data: AccCb, ctx: AppContext, user: TgUser) -> None:
    acc = await owned(ctx, cb, user, callback_data.key)
    if acc is None:
        return
    chat = await _user_chat(ctx, user, as_int(callback_data.arg))
    if chat is None:
        await cb.answer("not your chat", show_alert=True)
        return
    preset = chat.preset or (PRESET_PER_CATEGORY if chat.topics_possible else PRESET_GENERAL)
    await ctx.topics.apply_preset(chat, [acc], preset, by=user.id)
    text, kb = await delivery_screen(ctx, acc)
    await edit(cb, text, kb)
