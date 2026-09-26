"""`/progress` — the level map, interactive (T33 §3.4) — and the buttons under session messages.

Every option is a cycling button that re-renders the same message; choices are
remembered per user and account in `tg_users.prefs`. Works in private and in
groups (⏹ / 🗺 under a session summary live wherever the summary was posted).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from bson import ObjectId
from bson.errors import InvalidId

from wklabs.lib.accounts import Account
from wklabs.lib.progress import (
    PROGRESS_OPTIONS,
    current_level,
    due_count,
    levels_of,
    next_option,
    normalize_options,
    pick_levels,
    reverse_apply,
    stage_matrix,
    subject_index,
)
from wklabs.lib.sessions import DEFAULT_GAP, Session
from wklabs.lib.timeutil import utcnow
from wklabs.lib.users import TgUser

from .. import texts
from ..callbacks import ProgressCb, SessionCb
from ..context import AppContext
from ..keyboards import kb_progress
from ..render.common import span
from ..render.progress import render_map
from .common import edit, in_group

log = logging.getLogger(__name__)
router = Router(name="progress")
Json = dict[str, Any]
DAY_START_HOUR = 4  # the day boundary for `Δ day` (T32 §4); per-account later


def day_start(now: datetime, tz: ZoneInfo) -> datetime:
    local = now.astimezone(tz)
    start = local.replace(hour=DAY_START_HOUR, minute=0, second=0, microsecond=0)
    if local < start:
        start -= timedelta(days=1)
    return start


async def _window_events(
    ctx: AppContext, account: str, opts: dict[str, str], session: Session | None
) -> tuple[list[Json], str]:
    """Events that make the Δ: a session (given or the latest), today since 04:00, or 7 days."""
    tz = ZoneInfo(ctx.settings.tz)
    if session is None and opts["diff"] == "session":
        session = await ctx.sessions.current(account, DEFAULT_GAP)
        if session is None:
            recent = await ctx.sessions.recent(account, DEFAULT_GAP, limit=1)
            session = recent[0] if recent else None
    if session is not None:
        evs = await ctx.sessions.events(session)
        return evs, f"session {span(session.started_at, session.last_at, tz)}"
    now = utcnow()
    if opts["diff"] == "day":
        since, title = day_start(now, tz), "today"
    elif opts["diff"] == "week":
        since, title = now - timedelta(days=7), "7 days"
    else:
        return [], ""
    evs = [
        d
        async for d in ctx.db.events.find(
            {"account": account, "at": {"$gte": since}}, sort=[("at", 1)]
        )
    ]
    return evs, title


async def progress_screen(
    ctx: AppContext,
    user: TgUser,
    acc: Account,
    opts: dict[str, str],
    *,
    in_group: bool,
    session: Session | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    index = await subject_index(ctx.db)
    after = await stage_matrix(ctx.db, acc.key, index)
    level = await current_level(ctx.db, acc.key)
    events, title = await _window_events(ctx, acc.key, opts, session)
    before = reverse_apply(after, events, index) if events else (after if title else None)
    levels = pick_levels(levels_of(after), level, opts["levels"])
    text = render_map(
        acc.label,
        level,
        levels,
        after,
        before,
        opts,
        due=await due_count(ctx.db, acc.key, utcnow()),
        diff_title=title,
    )
    accounts = await ctx.accounts.for_owner(user.id)
    return text, kb_progress(acc.key, opts, accounts=accounts, in_group=in_group)


def user_opts(user: TgUser, key: str) -> dict[str, str]:
    per = user.prefs.get("progress") or {}
    return normalize_options(per.get(key) if isinstance(per, dict) else None)


async def _account_for(ctx: AppContext, user: TgUser, key: str | None) -> Account | None:
    accounts = await ctx.accounts.for_owner(user.id)
    if not accounts and user.is_admin:
        accounts = await ctx.accounts.list()
    if key:
        for a in accounts:
            if a.key == key:
                return a
        if user.is_admin:
            return await ctx.accounts.get(key)
        return None
    last = str(user.prefs.get("progress_last") or "")
    return next((a for a in accounts if a.key == last), accounts[0] if accounts else None)


@router.message(Command("progress"))
async def cmd_progress(message: Message, ctx: AppContext, user: TgUser) -> None:
    acc = await _account_for(ctx, user, None)
    if acc is None:
        await message.answer(texts.no_progress_accounts())
        return
    group = message.chat.type != "private"
    text, kb = await progress_screen(ctx, user, acc, user_opts(user, acc.key), in_group=group)
    await message.answer(text, reply_markup=kb)


@router.callback_query(ProgressCb.filter())
async def cb_progress(
    cb: CallbackQuery, callback_data: ProgressCb, ctx: AppContext, user: TgUser
) -> None:
    if callback_data.opt == "close":
        msg = cb.message
        if isinstance(msg, Message):
            try:
                await msg.delete()
            except Exception:
                await msg.edit_reply_markup(reply_markup=None)
        await cb.answer()
        return
    acc = await _account_for(ctx, user, callback_data.key)
    if acc is None:
        await cb.answer("not your account", show_alert=True)
        return
    fresh = await ctx.users.get(user.id) or user
    opts = user_opts(fresh, acc.key)
    opt = callback_data.opt
    if opt in PROGRESS_OPTIONS:
        values = [v for v, _ in PROGRESS_OPTIONS[opt]]
        picked = callback_data.arg if callback_data.arg in values else next_option(opt, opts[opt])
        opts[opt] = picked
        await ctx.users.set_pref(user.id, f"progress.{acc.key}.{opt}", opts[opt])
    elif opt == "acc":
        await ctx.users.set_pref(user.id, "progress_last", acc.key)
    text, kb = await progress_screen(ctx, fresh, acc, opts, in_group=in_group(cb))
    await edit(cb, text, kb)


# ------------------------------------------------------ session message buttons
async def _session(ctx: AppContext, cb: CallbackQuery, hex_id: str) -> Session | None:
    try:
        s = await ctx.sessions.get(ObjectId(hex_id))
    except InvalidId:
        s = None
    if s is None:
        await cb.answer("session not found", show_alert=True)
    return s


@router.callback_query(SessionCb.filter(F.action == "end"))
async def cb_session_end(
    cb: CallbackQuery, callback_data: SessionCb, ctx: AppContext, user: TgUser
) -> None:
    s = await _session(ctx, cb, callback_data.id)
    if s is None:
        return
    acc = await ctx.accounts.get(s.account)
    if acc is None or (acc.owner_tg_id != user.id and not user.is_admin):
        await cb.answer("not your session", show_alert=True)
        return
    if await ctx.sessions.close_now(s.id) is None:
        await cb.answer("already ended")
        return
    await cb.answer(texts.session_ended())
    try:
        await ctx.notifier.notify_sessions(accounts=[s.account])
    except Exception:
        log.exception("session pass after ⏹ failed")


@router.callback_query(SessionCb.filter(F.action == "map"))
async def cb_session_map(
    cb: CallbackQuery, callback_data: SessionCb, ctx: AppContext, user: TgUser
) -> None:
    s = await _session(ctx, cb, callback_data.id)
    if s is None:
        return
    acc = await ctx.accounts.get(s.account)
    msg = cb.message
    if acc is None or not isinstance(msg, Message):
        await cb.answer("account not found", show_alert=True)
        return
    opts = user_opts(user, acc.key)
    opts["diff"] = "session"
    text, kb = await progress_screen(ctx, user, acc, opts, in_group=in_group(cb), session=s)
    await msg.answer(text, reply_markup=kb)
    await cb.answer()
