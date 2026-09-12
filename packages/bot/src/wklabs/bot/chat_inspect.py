"""One `get_chat` + `get_chat_member(me)` → `Inspection` (rights snapshot for the registry)."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    ChatFullInfo,
    ChatMember,
    ChatMemberAdministrator,
    ChatMemberOwner,
    ChatMemberRestricted,
)

from wklabs.lib.chats import ADMIN, CHANNEL, GONE, KICKED, LEFT, Inspection, Rights

log = logging.getLogger(__name__)


def _status(member: ChatMember) -> str:
    raw = getattr(member, "status", "member")
    value = getattr(raw, "value", raw)
    return ADMIN if value == "creator" else str(value)


def inspection_from(info: ChatFullInfo, me: ChatMember) -> Inspection:
    status = _status(me)
    perms = info.permissions
    is_channel = str(info.type) == CHANNEL
    if isinstance(me, ChatMemberOwner):
        rights = Rights(can_post=True, can_manage_topics=True, can_delete=True, can_pin=True)
    elif isinstance(me, ChatMemberAdministrator):
        rights = Rights(
            can_post=bool(me.can_post_messages) if is_channel else True,
            can_manage_topics=bool(me.can_manage_topics),
            can_delete=bool(me.can_delete_messages),
            can_pin=bool(me.can_pin_messages),
        )
    elif isinstance(me, ChatMemberRestricted):
        rights = Rights(can_post=bool(me.can_send_messages), can_pin=bool(me.can_pin_messages))
    elif status in GONE:
        rights = Rights(can_post=False)
    else:  # plain member: the group-wide default permissions apply
        can_post = (
            True if perms is None or perms.can_send_messages is None else perms.can_send_messages
        )
        rights = Rights(can_post=bool(can_post) and not is_channel)
    return Inspection(
        type=str(info.type),
        title=info.title,
        is_forum=bool(info.is_forum),
        status=status,
        rights=rights,
        member_can_topics=bool(perms and perms.can_manage_topics),
    )


async def inspect_chat(bot: Bot, chat_id: int) -> Inspection | None:
    """None = the bot is not in that chat (or Telegram refused to tell)."""
    try:
        info = await bot.get_chat(chat_id)
        me = await bot.get_chat_member(chat_id, bot.id)
    except TelegramAPIError as exc:
        log.info("inspect %s failed: %s", chat_id, exc)
        return None
    return inspection_from(info, me)


async def verify_member(bot: Bot, chat_id: int, user_id: int) -> bool | None:
    """Is this user in the chat? None when the API cannot say (bot not admin there)."""
    try:
        m = await bot.get_chat_member(chat_id, user_id)
    except TelegramAPIError as exc:
        log.info("verify member %s in %s failed: %s", user_id, chat_id, exc)
        return None
    return _status(m) not in (LEFT, KICKED)
