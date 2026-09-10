"""Bot commands: public /start /ping (alive + your id); admin /status /sync /topics /help."""

from __future__ import annotations

import logging
from html import escape

from aiogram import Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import Message

from .context import AppContext
from .status_text import alive_text, status_text

log = logging.getLogger(__name__)
public = Router(name="wklabs-public")  # answers anyone: liveness + "your id" for TG_ADMIN_IDS
router = Router(name="wklabs")  # admin-only


class IsAdmin(BaseFilter):
    async def __call__(self, message: Message, ctx: AppContext) -> bool:  # type: ignore[override]
        uid = message.from_user.id if message.from_user else None
        ok = uid is not None and uid in ctx.settings.tg_admin_ids
        if not ok:
            log.info("ignored command from %s in chat %s", uid, message.chat.id)
        return ok


router.message.filter(IsAdmin())


@public.message(Command("start", "ping"))
async def cmd_start(message: Message, ctx: AppContext) -> None:
    uid = message.from_user.id if message.from_user else None
    await message.answer(await alive_text(ctx, uid, message.chat.id, message.message_thread_id))


HELP = (
    "<b>wanikani-labs bot</b>\n"
    "/status — last sync, levels, SRS, reviews due\n"
    "/sync — poll accounts now (and deliver digests)\n"
    "/sync_full — full refetch incl. subjects\n"
    "/topics — ensure forum topics exist\n"
    "/help — this"
)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP)


@router.message(Command("status"))
async def cmd_status(message: Message, ctx: AppContext) -> None:
    await message.answer(await status_text(ctx))


@router.message(Command("sync", "sync_full"))
async def cmd_sync(message: Message, ctx: AppContext) -> None:
    full = (message.text or "").startswith("/sync_full")
    if ctx.sync_lock.locked():
        await message.answer("⏳ sync already running")
        return
    note = await message.answer("⏳ syncing…")
    res = await ctx.run_sync(full=full, include_global=full, include_accounts=True)
    took = (res.finished_at - res.started_at).total_seconds() if res.finished_at else 0
    text = (
        f"{'✅' if res.ok else '❌'} {res.kind} in {took:.1f}s · fetched {res.total('fetched')}"
        f" · new {res.total('new')} · changed {res.total('changed')} · "
        f"events {len(res.events)} · requests {res.requests}"
    )
    if res.errors:
        text += "\n" + "\n".join(f"• {escape(e)}" for e in res.errors[:5])
    await note.edit_text(text)


@router.message(Command("topics"))
async def cmd_topics(message: Message, ctx: AppContext) -> None:
    created = await ctx.topics.ensure(ctx.bot)
    lines = [f"{k}: thread {v}" for k, v in sorted(ctx.topics.threads.items())]
    await message.answer(
        "topics"
        + (f" (created {len(created)})" if created else "")
        + ":\n"
        + "\n".join(escape(x) for x in lines)
    )
