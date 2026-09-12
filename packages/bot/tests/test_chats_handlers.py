"""Handlers over the chat registry: added by hand, picked in private, /setup, migration, screens."""

from datetime import UTC, datetime
from typing import cast

from aiogram import Bot
from aiogram.types import ChatMemberUpdated, Message

from wklabs.bot.handlers.chats import msg_chat_shared
from wklabs.bot.handlers.common import chat_card_screen, chats_screen, visible_chat
from wklabs.bot.handlers.membership import (
    on_migrate_to,
    on_my_chat_member,
    on_topic_closed,
    on_topic_edited,
)
from wklabs.bot.handlers.setup import cmd_setup
from wklabs.bot.middleware import thread_of
from wklabs.lib.chats import ADMIN, KICKED, LEFT, VIA_PICKED
from wklabs.lib.users import TgUser

from .helpers import BOT_ID, FakeBot, chat_info, ident, make_ctx, me_admin, me_left, me_member

NOW = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)


def user(id: int = 42, admin: bool = False) -> TgUser:
    return TgUser(id, "v", "V", "en", "admin" if admin else "user", "active", NOW, NOW)


def member_updated(chat_id: int, new: str, *, by: int = 42, title: str = "WK") -> ChatMemberUpdated:
    u = {"id": BOT_ID, "is_bot": True, "first_name": "bot"}
    member: dict = {"status": new, "user": u}
    if new == "administrator":
        member = me_admin().model_dump()
    elif new == "kicked":
        member["until_date"] = 0
    return ChatMemberUpdated.model_validate(
        {
            "chat": {"id": chat_id, "type": "supergroup", "title": title, "is_forum": True},
            "from": {"id": by, "is_bot": False, "first_name": "V"},
            "date": 1,
            "old_chat_member": {"status": "left", "user": u},
            "new_chat_member": member,
        }
    )


def message(chat_id: int, **extra) -> Message:
    d = {
        "message_id": 1,
        "date": 1,
        "chat": {"id": chat_id, "type": "supergroup", "title": "WK", "is_forum": True},
        "from": {"id": 42, "is_bot": False, "first_name": "V"},
    }
    d.update(extra)
    return Message.model_validate(d)


class Sink:
    """Collects `message.answer(...)` calls (aiogram methods are not awaited for real here)."""

    def __init__(self) -> None:
        self.out: list[tuple[str, object]] = []

    async def __call__(self, text: str, reply_markup=None, **kw) -> None:
        self.out.append((text, reply_markup))


async def test_added_by_hand_greets_and_registers(db):
    bot = FakeBot()
    ctx = make_ctx(db, bot=bot)
    bot.chats[-100] = chat_info(-100)
    bot.members[(-100, BOT_ID)] = me_admin()
    await ctx.users.ensure(42, first_name="V")
    await ctx.chats.ensure_private(42)  # 42 has talked to the bot in private → DM is possible
    await on_my_chat_member(member_updated(-100, "administrator"), ctx, user(), cast(Bot, bot))
    chat = await ctx.chats.get(-100)
    assert chat and chat.status == ADMIN and chat.topics_possible and chat.added_by == 42
    assert chat.is_member(42) and chat.greeted_at is not None
    assert bot.sent[-1][0] == 42 and "I'm in «WK» now" in bot.sent[-1][2]
    # a second rights change does not greet again
    await on_my_chat_member(member_updated(-100, "member"), ctx, user(), cast(Bot, bot))
    assert len(bot.sent) == 1
    # kicked → routes off, owner told
    acc = await ctx.accounts.create(ident(), "tok", owner_tg_id=42, source="test")
    await ctx.routes.ensure_account_routes(acc.key, -100, created_by=42)
    await on_my_chat_member(member_updated(-100, "kicked"), ctx, user(), cast(Bot, bot))
    chat = await ctx.chats.get(-100)
    assert chat and chat.status == KICKED and await ctx.routes.for_chat(-100) == []
    assert "Removed from" in bot.sent[-1][2]
    # unknown adder (never talked to the bot) → one line in the chat instead of a DM
    bot.chats[-200] = chat_info(-200, title="G", is_forum=False)
    bot.members[(-200, BOT_ID)] = me_member()
    await on_my_chat_member(
        member_updated(-200, "member", by=7, title="G"), ctx, user(7), cast(Bot, bot)
    )
    assert bot.sent[-1][0] == -200 and "/setup" in bot.sent[-1][2]


async def test_pick_chat_and_visibility(db):
    bot = FakeBot()
    ctx = make_ctx(db, bot=bot)
    bot.chats[-100] = chat_info(-100)
    bot.members[(-100, BOT_ID)] = me_admin()
    msg = message(42, chat_shared={"request_id": 1, "chat_id": -100, "title": "WK"})
    msg = msg.model_copy(update={"chat": {"id": 42, "type": "private", "first_name": "V"}})
    sink = Sink()
    object.__setattr__(msg, "answer", sink)
    await msg_chat_shared(msg, ctx, user(), cast(Bot, bot))
    assert sink.out[0][0].startswith("✅ «WK»") and "<b>WK</b> · forum" in sink.out[1][0]
    chat = await ctx.chats.get(-100)
    assert chat and chat.is_member(42) and chat.added_by == 42
    d = await db.tg_chats.find_one({"_id": -100})
    assert d and d["members"]["42"]["via"] == VIA_PICKED
    # someone else: not a known member; the bot is admin → live check says "left" → invisible
    assert await visible_chat(ctx, user(7), -100, bot=cast(Bot, bot)) is None
    bot.members[(-100, 7)] = me_member()
    seen = await visible_chat(ctx, user(7), -100, bot=cast(Bot, bot))
    assert seen is not None and seen.is_member(7)
    # bot admin sees everything; private ids resolve to the private chat
    assert await visible_chat(ctx, user(1, admin=True), -100) is not None
    priv = await visible_chat(ctx, user(42), 42)
    assert priv and priv.is_private
    # picked a chat the bot is not in
    msg = message(42, chat_shared={"request_id": 1, "chat_id": -300, "title": "Nope"})
    msg = msg.model_copy(update={"chat": {"id": 42, "type": "private", "first_name": "V"}})
    sink = Sink()
    object.__setattr__(msg, "answer", sink)
    await msg_chat_shared(msg, ctx, user(), cast(Bot, bot))
    assert "I'm not in that chat" in sink.out[-1][0]
    gone = await ctx.chats.get(-300)
    assert gone and gone.status == LEFT and gone.title == "Nope"
    _, kb = await chats_screen(ctx, user())
    names = [b.text for row in kb.inline_keyboard for b in row]
    assert names[0] == "🔒 private · here"
    assert "🗂 WK · forum" in names and "⚠️ Nope · removed me" in names


async def test_setup_light_and_card_in_group(db):
    bot = FakeBot()
    ctx = make_ctx(db, bot=bot)
    bot.chats[-100] = chat_info(-100)
    bot.members[(-100, BOT_ID)] = me_admin(topics=False)
    acc = await ctx.accounts.create(ident(), "tok", owner_tg_id=42, source="test")
    msg = message(-100, text="/setup")
    sink = Sink()
    object.__setattr__(msg, "answer", sink)
    await cmd_setup(msg, ctx, user(), cast(Bot, bot))
    text, kb = sink.out[0]
    assert "Missing right: Manage Topics" in text
    btns = [b.text for row in kb.inline_keyboard for b in row]  # type: ignore[union-attr]
    assert btns == ["📬 Deliver my digests here", "⚙️ Configure here", "⚙️ In private"]
    chat = await ctx.chats.get(-100)
    assert chat and chat.is_member(42) and not chat.topics_possible
    # the shared card shows everyone's routes with owners
    await ctx.routes.ensure_account_routes(acc.key, -100, created_by=42)
    text, kb = await chat_card_screen(ctx, user(7), chat, in_group=True)
    assert "📝 reviews · Vitalik (theirs)" in text
    btns = [b.text for row in kb.inline_keyboard for b in row]
    assert "🚫 Stop here" not in btns and "🧹 Close" in btns


async def test_migration_and_topic_events(db):
    bot = FakeBot()
    ctx = make_ctx(db, bot=bot)
    await ctx.chats.seen(-1, type="group", title="G", member=42)
    acc = await ctx.accounts.create(ident(), "tok", owner_tg_id=42, source="test")
    await ctx.routes.ensure_account_routes(acc.key, -1, created_by=42)
    await on_migrate_to(message(-1, migrate_to_chat_id=-100), ctx)
    assert [r.chat_id for r in await ctx.routes.for_account(acc.key)] == [-100, -100]
    new = await ctx.chats.get(-100)
    assert new and new.is_member(42) and new.type == "supergroup"
    await ctx.chats.remember_topic(-100, 7, "old")
    edited = message(
        -100, message_thread_id=7, is_topic_message=True, forum_topic_edited={"name": "new"}
    )
    await on_topic_edited(edited, ctx)
    await on_topic_closed(message(-100, message_thread_id=7, forum_topic_closed={}), ctx)
    chat = await ctx.chats.get(-100)
    assert chat and chat.topics[7].name == "new" and chat.topics[7].closed
    # topic learned from an ordinary message in it
    m = message(
        -100,
        message_thread_id=9,
        is_topic_message=True,
        text="hi",
        reply_to_message={
            "message_id": 9,
            "date": 1,
            "chat": {"id": -100, "type": "supergroup", "title": "WK"},
            "forum_topic_created": {"name": "Chat", "icon_color": 1},
        },
    )
    assert thread_of(m) == (9, "Chat")
    assert thread_of(message(-100, text="x")) is None
    await ctx.chats.seen(-100, type="supergroup", thread=thread_of(m))
    chat = await ctx.chats.get(-100)
    assert chat and chat.topics[9].name == "Chat"
    assert me_left().status == "left"
