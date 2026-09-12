"""Passive knowledge: the bot added/removed (`my_chat_member`), group migration, topic events."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import ChatMemberUpdated, Message

from wklabs.lib.chats import GONE, PRIVATE, VIA_ADDED, Chat
from wklabs.lib.users import TgUser

from .. import texts
from ..chat_inspect import inspect_chat
from ..context import AppContext
from ..keyboards import kb_greet

log = logging.getLogger(__name__)
router = Router(name="membership")


def _status(event: ChatMemberUpdated) -> str:
    raw = event.new_chat_member.status
    return str(getattr(raw, "value", raw))


@router.my_chat_member()
async def on_my_chat_member(
    event: ChatMemberUpdated, ctx: AppContext, user: TgUser, bot: Bot
) -> None:
    chat = event.chat
    status = _status(event)
    if str(chat.type) == PRIVATE:
        # the user blocked/unblocked the bot: their private routes follow
        if status in GONE:
            n = await ctx.routes.disable_chat(chat.id)
            log.info("user %s blocked the bot → %d private route(s) off", chat.id, n)
        await ctx.chats.set_status(chat.id, status)
        return
    if status in GONE:
        await ctx.chats.set_status(chat.id, status)
        n = await ctx.routes.disable_chat(chat.id)
        log.info("removed from %s (%s) → %d route(s) off", chat.id, status, n)
        await ctx.notifier._tell_owners_removed(chat.id, chat.title or str(chat.id))
        return
    insp = await inspect_chat(bot, chat.id)
    if insp is None:
        await ctx.chats.seen(chat.id, type=str(chat.type), title=chat.title, member=user.id)
        return
    registered = await ctx.chats.apply_inspection(chat.id, insp, added_by=user.id)
    await ctx.chats.add_member(chat.id, user.id, VIA_ADDED)
    log.info("in %s (%s) as %s by %s", chat.id, chat.title, status, user.id)
    if registered.greeted_at is None:
        await _greet(ctx, registered, user)


async def _greet(ctx: AppContext, chat: Chat, user: TgUser) -> None:
    """DM whoever added us (if they ever wrote to us in private), else one line in the chat."""
    sent: list[int] = []
    private = await ctx.chats.get(user.id)
    if user.is_active and private is not None and private.present:
        sent = await ctx.notifier.send(
            user.id, None, [texts.greet_dm(chat)], reply_markup=kb_greet(chat)
        )
    if not sent and chat.can_post:
        sent = await ctx.notifier.send(chat.id, None, [texts.greet_chat()])
    if sent or ctx.notifier.dry_run:
        await ctx.chats.set_greeted(chat.id)


@router.message(F.migrate_to_chat_id)
async def on_migrate_to(message: Message, ctx: AppContext) -> None:
    new = message.migrate_to_chat_id
    assert new is not None
    await ctx.chats.migrate(message.chat.id, new)
    await ctx.routes.migrate_chat(message.chat.id, new)


@router.message(F.migrate_from_chat_id)
async def on_migrate_from(message: Message, ctx: AppContext) -> None:
    old = message.migrate_from_chat_id
    assert old is not None
    await ctx.chats.migrate(old, message.chat.id)
    await ctx.routes.migrate_chat(old, message.chat.id)


@router.message(F.forum_topic_edited)
async def on_topic_edited(message: Message, ctx: AppContext) -> None:
    edited = message.forum_topic_edited
    if edited is None or not edited.name or not message.message_thread_id:
        return
    await ctx.chats.remember_topic(message.chat.id, message.message_thread_id, edited.name)
    await ctx.routes.rename_thread(message.chat.id, message.message_thread_id, edited.name)


@router.message(F.forum_topic_closed)
async def on_topic_closed(message: Message, ctx: AppContext) -> None:
    if message.message_thread_id:
        await ctx.chats.topic_closed(message.chat.id, message.message_thread_id, True)


@router.message(F.forum_topic_reopened)
async def on_topic_reopened(message: Message, ctx: AppContext) -> None:
    if message.message_thread_id:
        await ctx.chats.topic_closed(message.chat.id, message.message_thread_id, False)
