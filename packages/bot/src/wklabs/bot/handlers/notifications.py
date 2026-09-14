"""Notifications of an account: kind → route (card, settings L1/L2, preview) → target picker.

Works in private and in groups (route screens are reachable from a chat's
🧭 Routes here); every press re-checks `can_edit`. The picker context (account,
kind, mode, route) lives in the FSM so callback data stays under 64 bytes.
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from bson import ObjectId
from bson.errors import InvalidId

from wklabs.lib.accounts import Account
from wklabs.lib.chats import Chat
from wklabs.lib.delivery import (
    ACCOUNT_KINDS,
    ADDABLE_KINDS,
    BLUE,
    KIND_COLOR,
    PRESET_GENERAL,
    PRESET_PER_CATEGORY,
    Route,
    preset_topic_name,
)
from wklabs.lib.notify_settings import BY_KEY, effective
from wklabs.lib.users import TgUser

from .. import texts
from ..callbacks import AccCb, ChatCb, PickTarget, RouteCb, TargetCb, TopicName
from ..context import AppContext
from ..keyboards import (
    kb_add_kind,
    kb_back_accounts,
    kb_cancel,
    kb_kind,
    kb_notifications,
    kb_pick_chat_target,
    kb_pick_topic,
)
from ..topics import PresetResult
from .common import (
    can_edit,
    edit,
    in_group,
    owned,
    route_more_screen,
    route_screen,
    routes_with_chats,
    visible_chat,
)

log = logging.getLogger(__name__)
router = Router(name="notifications")
Json = dict[str, Any]


# ------------------------------------------------------------- screens
async def notifications_screen(ctx: AppContext, acc: Account) -> tuple[str, InlineKeyboardMarkup]:
    rows = await routes_with_chats(ctx, acc)
    chat_ids = sorted({c.id for _, c in rows})
    if not chat_ids and acc.owner_tg_id is not None:
        chat_ids = [acc.owner_tg_id]
    subjects: list[tuple[Chat, Route | None, bool]] = []
    for cid in chat_ids:
        chat = await ctx.chats.get(cid) or await ctx.chats.ensure_private(cid)
        found = [
            r
            for r in await ctx.routes.for_chat(cid, include_disabled=True)
            if r.account is None and r.kind == "subjects"
        ]
        route = found[0] if found else None
        mine = bool(route and acc.owner_tg_id in route.subscribers)
        subjects.append((chat, route, mine))
    kinds = list(ACCOUNT_KINDS)
    return texts.notifications(acc, rows, kinds), kb_notifications(acc, kinds, subjects)


async def kind_screen(ctx: AppContext, acc: Account, kind: str) -> tuple[str, InlineKeyboardMarkup]:
    rows = [(r, c) for r, c in await routes_with_chats(ctx, acc) if r.kind == kind]
    return texts.kind_screen(acc, kind, rows), kb_kind(acc, kind, rows)


def _back_for(route: Route, *, group: bool) -> tuple[str, AccCb | ChatCb]:
    if group or route.account is None:
        return "« Chat", ChatCb(chat=route.chat_id, action="routes")
    return f"« {route.icon} {route.title}", AccCb(key=route.account, action="kind", arg=route.kind)


async def _route(ctx: AppContext, cb: CallbackQuery, hex_id: str) -> Route | None:
    try:
        route = await ctx.routes.get(ObjectId(hex_id))
    except InvalidId:
        route = None
    if route is None:
        await cb.answer("route not found", show_alert=True)
    return route


# ---------------------------------------------------------- account hub
@router.callback_query(AccCb.filter(F.action == "notif"))
async def cb_notifications(
    cb: CallbackQuery, callback_data: AccCb, ctx: AppContext, user: TgUser, state: FSMContext
) -> None:
    acc = await owned(ctx, cb, user, callback_data.key)
    if acc is None:
        return
    await state.clear()
    text, kb = await notifications_screen(ctx, acc)
    await edit(cb, text, kb)


@router.callback_query(AccCb.filter(F.action == "kind"))
async def cb_kind(
    cb: CallbackQuery, callback_data: AccCb, ctx: AppContext, user: TgUser, state: FSMContext
) -> None:
    acc = await owned(ctx, cb, user, callback_data.key)
    if acc is None:
        return
    await state.clear()
    text, kb = await kind_screen(ctx, acc, callback_data.arg)
    await edit(cb, text, kb)


@router.callback_query(AccCb.filter(F.action == "addkind"))
async def cb_add_kind(
    cb: CallbackQuery, callback_data: AccCb, ctx: AppContext, user: TgUser, state: FSMContext
) -> None:
    acc = await owned(ctx, cb, user, callback_data.key)
    if acc is None:
        return
    await state.clear()
    await edit(cb, texts.add_kind(acc), kb_add_kind(acc))


@router.callback_query(AccCb.filter(F.action == "subj"))
async def cb_subjects_toggle(
    cb: CallbackQuery, callback_data: AccCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    acc = await owned(ctx, cb, user, callback_data.key)
    if acc is None:
        return
    try:
        chat_id = int(callback_data.arg)
    except ValueError:
        chat_id = 0
    chat = await visible_chat(ctx, user, chat_id, bot=bot)
    if chat is None:
        await cb.answer("not your chat", show_alert=True)
        return
    current = [
        r
        for r in await ctx.routes.for_chat(chat.id, include_disabled=True)
        if r.account is None and r.kind == "subjects"
    ]
    if current and user.id in current[0].subscribers:
        await ctx.routes.unsubscribe("subjects", chat.id, user.id)
    else:
        await ctx.routes.subscribe("subjects", chat.id, user.id)
    text, kb = await notifications_screen(ctx, acc)
    await edit(cb, text, kb)


# ------------------------------------------------------------ route card
@router.callback_query(RouteCb.filter(F.action == "card"))
async def cb_route(
    cb: CallbackQuery, callback_data: RouteCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    route = await _route(ctx, cb, callback_data.id)
    if route is None:
        return
    back_text, back_cb = _back_for(route, group=in_group(cb))
    text, kb = await route_screen(ctx, user, route, bot=bot, back_text=back_text, back_cb=back_cb)
    await edit(cb, text, kb)


@router.callback_query(RouteCb.filter(F.action == "toggle"))
async def cb_route_toggle(
    cb: CallbackQuery, callback_data: RouteCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    route = await _route(ctx, cb, callback_data.id)
    if route is None:
        return
    perm = await can_edit(ctx, user, route, bot=bot)
    if not perm.toggle:
        await cb.answer(texts.not_allowed(), show_alert=True)
        return
    if route.account is None:  # global: toggle = my subscription
        if user.id in route.subscribers:
            await ctx.routes.unsubscribe(route.kind, route.chat_id, user.id)
        else:
            await ctx.routes.subscribe(route.kind, route.chat_id, user.id)
    else:
        await ctx.routes.set_enabled(route.id, not route.enabled)
    fresh = await ctx.routes.get(route.id) or route
    back_text, back_cb = _back_for(fresh, group=in_group(cb))
    text, kb = await route_screen(ctx, user, fresh, bot=bot, back_text=back_text, back_cb=back_cb)
    await edit(cb, text, kb)


@router.callback_query(RouteCb.filter(F.action.in_({"set", "set2"})))
async def cb_route_set(
    cb: CallbackQuery, callback_data: RouteCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    """Cycle one setting; `set` returns to the card, `set2` to ⚙️ More…"""
    route = await _route(ctx, cb, callback_data.id)
    if route is None:
        return
    setting = BY_KEY.get(callback_data.arg)
    if setting is None or not setting.applies(route.kind):
        await cb.answer("unknown setting", show_alert=True)
        return
    perm = await can_edit(ctx, user, route, bot=bot)
    if not perm.settings:
        await cb.answer(texts.not_allowed(), show_alert=True)
        return
    value = setting.next_value(effective(route)[setting.key])
    await ctx.routes.set_setting(route.id, setting.key, value, by=user.id)
    fresh = await ctx.routes.get(route.id) or route
    if callback_data.action == "set2":
        text, kb = await route_more_screen(ctx, fresh)
    else:
        back_text, back_cb = _back_for(fresh, group=in_group(cb))
        text, kb = await route_screen(
            ctx, user, fresh, bot=bot, back_text=back_text, back_cb=back_cb
        )
    await edit(cb, text, kb)


@router.callback_query(RouteCb.filter(F.action.in_({"more", "reset"})))
async def cb_route_more(
    cb: CallbackQuery, callback_data: RouteCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    route = await _route(ctx, cb, callback_data.id)
    if route is None:
        return
    perm = await can_edit(ctx, user, route, bot=bot)
    if not perm.settings:
        await cb.answer(texts.not_allowed(), show_alert=True)
        return
    note = None
    if callback_data.action == "reset":
        await ctx.routes.reset_settings(route.id, by=user.id)
        route = await ctx.routes.get(route.id) or route
        note = "↩️ defaults restored"
    text, kb = await route_more_screen(ctx, route, note=note)
    await edit(cb, text, kb)


@router.callback_query(RouteCb.filter(F.action == "preview"))
async def cb_route_preview(
    cb: CallbackQuery, callback_data: RouteCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    """The last closed session, rendered with this route's settings, sent to its target."""
    route = await _route(ctx, cb, callback_data.id)
    if route is None:
        return
    perm = await can_edit(ctx, user, route, bot=bot)
    if not perm.any:
        await cb.answer(texts.not_allowed(), show_alert=True)
        return
    err = await ctx.notifier.preview_session(route)
    await cb.answer(texts.preview_result(err), show_alert=err is not None)


@router.callback_query(RouteCb.filter(F.action == "test"))
async def cb_route_test(
    cb: CallbackQuery, callback_data: RouteCb, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    route = await _route(ctx, cb, callback_data.id)
    if route is None:
        return
    perm = await can_edit(ctx, user, route, bot=bot)
    if not perm.any:
        await cb.answer(texts.not_allowed(), show_alert=True)
        return
    _, err = await ctx.notifier.send_one(route.chat_id, route.thread_id, texts.test_message())
    await cb.answer(texts.test_result(err), show_alert=err is not None)


# --------------------------------------------------------- target picker
async def _start_pick(
    cb: CallbackQuery, state: FSMContext, ctx: AppContext, user: TgUser, data: Json, *, bot: Bot
) -> None:
    await state.set_state(PickTarget.chat)
    await state.update_data(pick=data)
    await _show_chats(cb, ctx, user, data, bot=bot)


async def _show_chats(
    cb: CallbackQuery, ctx: AppContext, user: TgUser, data: Json, *, bot: Bot
) -> None:
    acc = await ctx.accounts.get(str(data.get("key") or ""))
    label = acc.label if acc else None
    mode = str(data.get("mode") or "mv")
    current: int | None = None
    chats = [c for c in await ctx.chats.visible_to(user.id, admin=user.is_admin) if c.can_post]
    back: AccCb | RouteCb
    if data.get("route"):
        route = await ctx.routes.get(ObjectId(str(data["route"])))
        if route is not None:
            current = route.chat_id
            perm = await can_edit(ctx, user, route, bot=bot)
            if not perm.target_any:  # chat admin: only within this chat
                chats = [c for c in chats if c.id == route.chat_id]
        back = RouteCb(id=str(data["route"]), action="card")
    else:
        back = AccCb(key=str(data.get("key")), action="notif")
    text = texts.pick_chat_target(label, str(data.get("kind") or ""), mode=mode)
    await edit(cb, text, kb_pick_chat_target(chats, current, back))


@router.callback_query(AccCb.filter(F.action.in_({"add", "moveall"})))
async def cb_pick_start(
    cb: CallbackQuery,
    callback_data: AccCb,
    ctx: AppContext,
    user: TgUser,
    state: FSMContext,
    bot: Bot,
) -> None:
    acc = await owned(ctx, cb, user, callback_data.key)
    if acc is None:
        return
    if callback_data.action == "moveall":
        data: Json = {"key": acc.key, "kind": "", "mode": "all", "route": ""}
    else:
        kind = callback_data.arg if callback_data.arg in ADDABLE_KINDS else ADDABLE_KINDS[0]
        data = {"key": acc.key, "kind": kind, "mode": "add", "route": ""}
    await _start_pick(cb, state, ctx, user, data, bot=bot)


@router.callback_query(RouteCb.filter(F.action == "target"))
async def cb_route_target(
    cb: CallbackQuery,
    callback_data: RouteCb,
    ctx: AppContext,
    user: TgUser,
    state: FSMContext,
    bot: Bot,
) -> None:
    route = await _route(ctx, cb, callback_data.id)
    if route is None:
        return
    perm = await can_edit(ctx, user, route, bot=bot)
    if not perm.target:
        await cb.answer(texts.not_allowed(), show_alert=True)
        return
    data: Json = {
        "key": route.account or "",
        "kind": route.kind,
        "mode": "mv",
        "route": str(route.id),
    }
    await _start_pick(cb, state, ctx, user, data, bot=bot)


@router.callback_query(TargetCb.filter(), StateFilter(PickTarget))
async def cb_target(
    cb: CallbackQuery,
    callback_data: TargetCb,
    ctx: AppContext,
    user: TgUser,
    state: FSMContext,
    bot: Bot,
) -> None:
    data: Json = dict((await state.get_data()).get("pick") or {})
    if not data:
        await state.clear()
        await edit(cb, texts.stale(), kb_back_accounts())
        return
    if callback_data.chat == 0:  # back to the chat step
        await state.set_state(PickTarget.chat)
        await _show_chats(cb, ctx, user, data, bot=bot)
        return
    chat = await visible_chat(ctx, user, callback_data.chat, bot=bot)
    if chat is None or not chat.can_post:
        await cb.answer("I can't post there — check /chats", show_alert=True)
        return
    acc = await ctx.accounts.get(str(data.get("key") or ""))
    mode = str(data.get("mode") or "mv")
    if mode == "all":
        if acc is None:
            await cb.answer("account not found", show_alert=True)
            return
        preset = chat.preset or (PRESET_PER_CATEGORY if chat.topics_possible else PRESET_GENERAL)
        res = await ctx.topics.apply_preset(chat, [acc], preset, by=user.id)
        await state.clear()
        text, kb = await notifications_screen(ctx, acc)
        note = texts.preset_done(res.labels, res.created, res.reused, res.general)
        await edit(cb, f"{note}\n{text}", kb)
        return
    kind = str(data.get("kind") or "")
    if callback_data.thread == "" and chat.is_forum:
        await state.set_state(PickTarget.topic)
        auto = preset_topic_name(
            chat.preset or PRESET_PER_CATEGORY, kind, acc.label if acc else None
        )
        current: int | None = None
        if data.get("route"):
            r = await ctx.routes.get(ObjectId(str(data["route"])))
            current = r.thread_id if r and r.chat_id == chat.id else None
        await edit(cb, texts.pick_topic(chat, kind), kb_pick_topic(chat, auto, current))
        return
    if callback_data.thread == "n":
        if not chat.topics_possible:
            await cb.answer("I can't create topics here", show_alert=True)
            return
        await state.set_state(TopicName.name)
        await state.update_data(topic={"chat": chat.id, "thread": 0, "resume": data})
        await edit(cb, texts.topic_name_prompt(chat, None), kb_cancel())
        return
    thread_id, title = await _resolve_thread(ctx, chat, callback_data.thread, kind, acc)
    if thread_id is None and callback_data.thread not in ("", "g", "a"):
        await cb.answer("topic not found — pick another", show_alert=True)
        return
    await state.clear()
    text, kb = await apply_target(
        ctx, user, data, chat, thread_id, title, bot=bot, group=in_group(cb)
    )
    await edit(cb, text, kb)


async def _resolve_thread(
    ctx: AppContext, chat: Chat, choice: str, kind: str, acc: Account | None
) -> tuple[int | None, str | None]:
    if choice in ("", "g") or not chat.is_forum:
        return None, None
    if choice == "a":
        name = preset_topic_name(
            chat.preset or PRESET_PER_CATEGORY, kind, acc.label if acc else None
        )
        if name is None or not chat.topics_possible:
            return None, None
        topic = await ctx.topics.find_or_create(
            chat, name, KIND_COLOR.get(kind, BLUE), PresetResult()
        )
        return topic.thread_id, topic.name
    try:
        tid = int(choice)
    except ValueError:
        return None, None
    topic = chat.topic(tid)
    return (tid, topic.name) if topic else (None, None)


async def apply_target(
    ctx: AppContext,
    user: TgUser,
    data: Json,
    chat: Chat,
    thread_id: int | None,
    title: str | None,
    *,
    bot: Bot | None,
    group: bool = False,
) -> tuple[str, InlineKeyboardMarkup]:
    """Move (mode mv) or add (mode add) the route to chat/topic; returns the route screen."""
    mode = str(data.get("mode") or "mv")
    key = str(data.get("key") or "") or None
    kind = str(data.get("kind") or "")
    if mode == "mv" and data.get("route"):
        old = await ctx.routes.get(ObjectId(str(data["route"])))
        if old is None:
            return texts.stale(), kb_back_accounts()
        route = await ctx.routes.move_route(old, chat.id, thread_id, title, by=user.id)
    else:
        route = await ctx.routes.add_target(key, kind, chat.id, thread_id, title, by=user.id)
    back_text, back_cb = _back_for(route, group=group)
    return await route_screen(
        ctx,
        user,
        route,
        bot=bot,
        back_text=back_text,
        back_cb=back_cb,
        note=texts.target_set(route, chat),
    )


async def resume_target(
    ctx: AppContext,
    user: TgUser,
    message: Message,
    resume: Json,
    chat: Chat,
    thread_id: int,
    title: str,
) -> None:
    """A topic was created from the picker → finish the pending target change."""
    text, kb = await apply_target(
        ctx, user, resume, chat, thread_id, title, bot=None, group=message.chat.type != "private"
    )
    await message.answer(text, reply_markup=kb)
