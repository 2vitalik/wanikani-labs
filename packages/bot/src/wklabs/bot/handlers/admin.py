"""Admin-only: /admin hub (users, accounts, sync, status), approve/block, /sync /sync_full."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from wklabs.lib.users import ACTIVE, BLOCKED, TgUser

from .. import texts
from ..callbacks import AdminCb
from ..context import AppContext
from ..keyboards import (
    kb_admin_accounts,
    kb_admin_home,
    kb_admin_user,
    kb_admin_users,
    kb_back_admin,
)
from ..status_text import status_text
from .common import IsAdmin, as_int, edit

router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def _home(ctx: AppContext) -> tuple[str, object]:
    return texts.admin_home(), kb_admin_home(
        await ctx.users.counts(), len(await ctx.accounts.list(status=None))
    )


@router.message(Command("admin"), F.chat.type == "private")
async def cmd_admin(message: Message, ctx: AppContext) -> None:
    text, kb = await _home(ctx)
    await message.answer(text, reply_markup=kb)  # type: ignore[arg-type]


@router.callback_query(AdminCb.filter(F.action == "home"))
async def cb_home(cb: CallbackQuery, ctx: AppContext) -> None:
    text, kb = await _home(ctx)
    await edit(cb, text, kb)  # type: ignore[arg-type]


@router.callback_query(AdminCb.filter(F.action == "users"))
async def cb_users(cb: CallbackQuery, ctx: AppContext) -> None:
    users = await ctx.users.list()
    await edit(cb, texts.admin_users(users), kb_admin_users(users))


@router.callback_query(AdminCb.filter(F.action.in_({"user", "approve", "block"})))
async def cb_user(cb: CallbackQuery, callback_data: AdminCb, ctx: AppContext, user: TgUser) -> None:
    uid = as_int(callback_data.arg)
    target = await ctx.users.get(uid)
    if target is None:
        await cb.answer("user not found", show_alert=True)
        return
    if callback_data.action == "approve" and target.status != ACTIVE:
        await ctx.users.set_status(uid, ACTIVE, by=user.id)
        await ctx.notifier.send(uid, None, [texts.access_granted()])
    elif callback_data.action == "block" and not target.is_admin:
        await ctx.users.set_status(uid, BLOCKED, by=user.id)
    target = await ctx.users.get(uid)
    assert target is not None
    accounts = await ctx.accounts.for_owner(uid, include_removed=True)
    await edit(cb, texts.admin_user(target, accounts), kb_admin_user(target))


@router.callback_query(AdminCb.filter(F.action == "accounts"))
async def cb_accounts(cb: CallbackQuery, ctx: AppContext) -> None:
    accounts = await ctx.accounts.list(status=None)
    await edit(cb, texts.admin_accounts(accounts), kb_admin_accounts(accounts))


@router.callback_query(AdminCb.filter(F.action == "status"))
async def cb_status(cb: CallbackQuery, ctx: AppContext) -> None:
    accounts = await ctx.accounts.list(status=None)
    await edit(cb, await status_text(ctx, accounts, admin=True), kb_back_admin())


@router.callback_query(AdminCb.filter(F.action.in_({"sync", "sync_full"})))
async def cb_sync(cb: CallbackQuery, callback_data: AdminCb, ctx: AppContext) -> None:
    if ctx.sync_lock.locked():
        await cb.answer("⏳ sync already running", show_alert=True)
        return
    await cb.answer("⏳ syncing…")
    full = callback_data.action == "sync_full"
    res = await ctx.run_sync(full=full, include_global=full, include_accounts=True)
    await edit(cb, texts.sync_result(res), kb_back_admin())


@router.message(Command("sync", "sync_full"))
async def cmd_sync(message: Message, ctx: AppContext) -> None:
    full = (message.text or "").startswith("/sync_full")
    if ctx.sync_lock.locked():
        await message.answer("⏳ sync already running")
        return
    note = await message.answer("⏳ syncing…")
    res = await ctx.run_sync(full=full, include_global=full, include_accounts=True)
    await note.edit_text(texts.sync_result(res))
