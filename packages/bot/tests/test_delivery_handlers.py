"""Phase 2: settings in delivery, permissions, target picker, topics from the UI, subscriptions."""

from datetime import UTC, datetime
from typing import cast
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import Message

from wklabs.bot.digest import render
from wklabs.bot.handlers.chats import cb_global_toggle, msg_topic_name
from wklabs.bot.handlers.common import CHAT_ADMIN, FULL, VIEW, can_edit, route_screen
from wklabs.bot.handlers.delivery import (
    _resolve_thread,
    apply_target,
    category_screen,
    delivery_screen,
)
from wklabs.lib.chats import ADMIN, Inspection, Rights
from wklabs.lib.delivery import PRESET_PER_ACCOUNT, PRESET_PER_CATEGORY

from .helpers import BOT_ID, FakeBot, ident, make_ctx, me_admin, me_member
from .test_chats_handlers import Sink, user

NOW = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
FORUM = Inspection(
    type="supergroup",
    title="WK",
    is_forum=True,
    status=ADMIN,
    rights=Rights(can_post=True, can_manage_topics=True),
)
AT = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def pmsg(text: str) -> Message:
    return Message.model_validate(
        {
            "message_id": 1,
            "date": 1,
            "chat": {"id": 42, "type": "private", "first_name": "V"},
            "from": {"id": 42, "is_bot": False, "first_name": "V"},
            "text": text,
        }
    )


def ev(kind: str, sid: int, hid: int, correct: bool = True, **meta) -> dict:
    return {
        "kind": kind,
        "at": AT,
        "account": "07fff792",
        "subject_id": sid,
        "subject_type": "kanji",
        "meta": {"count": 1, "correct": correct, "meaning_wrong": 0, "reading_wrong": 0, **meta},
        "history_id": hid,
        "notified_at": None,
    }


def test_render_items():
    tz = ZoneInfo("UTC")
    subjects = {
        1: {"_id": 1, "type": "kanji", "characters": "火"},
        2: {"_id": 2, "type": "kanji", "characters": "水"},
    }
    events = [ev("reviewed", 1, 1, True), ev("reviewed", 2, 2, False), ev("started", 1, 3)]
    full = render("reviews", "V", events, subjects, tz)[0]
    assert "✅" in full and "❌" in full and "📖 lessons" in full
    wrong = render("reviews", "V", events, subjects, tz, items="wrong")[0]
    assert "❌" in wrong and "✅ " not in wrong.split("\n", 1)[1] and "📖 lessons" not in wrong
    none = render("reviews", "V", events, subjects, tz, items="none")[0]
    assert none.count("\n") == 0 and "2 reviews" in none


async def test_silent_and_items_in_delivery(db):
    bot = FakeBot()
    ctx = make_ctx(db, bot=bot)
    acc = await ctx.accounts.create(ident(), "tok", owner_tg_id=42, source="test")
    await ctx.chats.ensure_private(42)
    r = (await ctx.routes.ensure_account_routes(acc.key, 42, created_by=42))[0]
    await ctx.routes.set_setting(r.id, "silent", True, by=42)
    await ctx.routes.set_setting(r.id, "items", "none", by=42)
    await db.col("subjects").insert_one({"_id": 1, "type": "kanji", "level": 2, "characters": "火"})
    await db.events.insert_many([ev("reviewed", 1, 1, False)])
    sent_kw: list[dict] = []
    orig = bot.send_message

    async def spy(chat_id, text, **kw):
        sent_kw.append(kw)
        return await orig(chat_id, text, **kw)

    bot.send_message = spy  # type: ignore[method-assign]
    assert await ctx.notifier.notify_pending() == 1
    assert sent_kw[0]["disable_notification"] is True
    assert "火" not in bot.sent[0][2] and "1 reviews" in bot.sent[0][2]


async def test_can_edit_and_route_screen(db):
    bot = FakeBot()
    ctx = make_ctx(db, bot=bot, admin_ids=[1])
    acc = await ctx.accounts.create(ident(), "tok", owner_tg_id=42, source="test")
    chat = await ctx.chats.apply_inspection(-100, FORUM)
    await ctx.chats.add_member(-100, 42, "added")
    await ctx.chats.add_member(-100, 7, "message")
    route = (await ctx.routes.ensure_account_routes(acc.key, -100, created_by=42))[0]
    b = cast(Bot, bot)
    assert await can_edit(ctx, user(42), route, bot=b) == FULL
    assert await can_edit(ctx, user(1, admin=True), route, bot=b) == FULL
    assert await can_edit(ctx, user(7), route, bot=b) == VIEW  # plain member: view only
    bot.members[(-100, 7)] = me_admin()  # chat admin → within the chat
    ctx.admin_cache.clear()
    assert await can_edit(ctx, user(7), route, bot=b) == CHAT_ADMIN
    # global route: any known member touches their own subscription + shared settings
    subj = await ctx.routes.subscribe("subjects", -100, 42)
    perm = await can_edit(ctx, user(9), subj, bot=b)
    assert not perm.any
    await ctx.chats.add_member(-100, 9, "message")
    perm = await can_edit(ctx, user(9), subj, bot=b)
    assert perm.toggle and perm.settings and not perm.target
    # route screen for the owner shows settings and target buttons; view-only for a stranger
    from wklabs.bot.callbacks import AccCb

    text, kb = await route_screen(
        ctx, user(42), route, bot=b, back_text="« back", back_cb=AccCb(key=acc.key, action="cat")
    )
    labels = [x.text for row in kb.inline_keyboard for x in row]
    assert "✅ on" in labels and "🔕 Silent: off" in labels and "📄 Items: all" in labels
    assert "📍 Change target" in labels and "silent — no notification sound" in text
    text, kb = await route_screen(
        ctx, user(9), route, bot=b, back_text="« back", back_cb=AccCb(key=acc.key, action="cat")
    )
    labels = [x.text for row in kb.inline_keyboard for x in row]
    assert "view only" in text and "✅ on" not in labels and "📨 Send test" in labels
    assert chat.topics_possible


async def test_target_picker_apply_and_resolve(db):
    bot = FakeBot()
    ctx = make_ctx(db, bot=bot)
    acc = await ctx.accounts.create(ident(), "tok", owner_tg_id=42, source="test")
    await ctx.chats.ensure_private(42)
    priv_routes = await ctx.routes.ensure_account_routes(acc.key, 42, created_by=42)
    forum = await ctx.chats.apply_inspection(-100, FORUM)
    await ctx.chats.add_member(-100, 42, "added")
    await ctx.chats.remember_topic(-100, 5, "Family")
    forum = await ctx.chats.get(-100)
    assert forum is not None
    # "a" → auto topic per the chat's preset (default per category), created on demand
    tid, title = await _resolve_thread(ctx, forum, "a", "reviews", acc)
    assert title == "📝 Vitalik · reviews" and bot.topics[-1][1] == title and tid == 7
    # known topic by id, General, unknown
    assert await _resolve_thread(ctx, forum, "5", "reviews", acc) == (5, "Family")
    assert await _resolve_thread(ctx, forum, "g", "reviews", acc) == (None, None)
    assert await _resolve_thread(ctx, forum, "99", "reviews", acc) == (None, None)
    # move the private reviews route into the forum's Family topic
    data = {"key": acc.key, "cat": "reviews", "mode": "mv", "route": str(priv_routes[0].id)}
    text, kb = await apply_target(ctx, user(42), data, forum, 5, "Family", bot=cast(Bot, bot))
    assert "✅ → WK › Family" in text
    live = await ctx.routes.for_target(acc.key, "reviews")
    assert [(r.chat_id, r.thread_id) for r in live] == [(-100, 5)]
    # "also deliver to" keeps the existing one and adds private back
    data = {"key": acc.key, "cat": "reviews", "mode": "add", "route": ""}
    priv = await ctx.chats.get(42)
    assert priv is not None
    await apply_target(ctx, user(42), data, priv, None, None, bot=cast(Bot, bot))
    live = await ctx.routes.for_target(acc.key, "reviews")
    assert sorted(r.chat_id for r in live) == [-100, 42]
    # screens
    text, kb = await delivery_screen(ctx, acc)
    assert "📝 reviews → WK › Family" in text and "📝 reviews → private" in text
    labels = [x.text for row in kb.inline_keyboard for x in row]
    assert labels[:2] == ["📝 reviews", "🏆 milestones"] and "➡️ Move all to…" in labels
    text, kb = await category_screen(ctx, acc, "reviews")
    labels = [x.text for row in kb.inline_keyboard for x in row]
    assert labels[0] == "✅ WK › Family" and labels[-2] == "➕ Also deliver to…"
    # per-account preset later reuses the bot's own topic, not Family
    res = await ctx.topics.apply_preset(forum, [acc], PRESET_PER_ACCOUNT, by=42)
    assert res.created == ["Vitalik"]
    assert await ctx.chats.get(-100) is not None and PRESET_PER_CATEGORY


async def test_topic_from_ui_and_subscriptions(db):
    bot = FakeBot()
    ctx = make_ctx(db, bot=bot)
    await ctx.chats.apply_inspection(-100, FORUM)
    await ctx.chats.add_member(-100, 42, "added")
    await ctx.chats.remember_topic(-100, 5, "Family")

    class State:
        def __init__(self, data):
            self.data = data
            self.cleared = False

        async def get_data(self):
            return self.data

        async def clear(self):
            self.cleared = True

    # create a new topic by name (no pending target)
    msg = pmsg("Study log")
    sink = Sink()
    object.__setattr__(msg, "answer", sink)
    st = State({"topic": {"chat": -100, "thread": 0, "resume": None}})
    await msg_topic_name(msg, ctx, user(42), st, cast(Bot, bot))  # type: ignore[arg-type]
    assert st.cleared and bot.topics == [(-100, "Study log")]
    assert sink.out[-1][0].startswith("✅ Topic «Study log» created.")
    chat = await ctx.chats.get(-100)
    assert chat and chat.topic_by_name("Study log") and chat.topic_by_name("Study log").by_bot  # type: ignore[union-attr]
    # rename the bot's own topic
    tid = chat.topic_by_name("Study log").thread_id  # type: ignore[union-attr]
    msg2 = pmsg("Log")
    sink = Sink()
    object.__setattr__(msg2, "answer", sink)
    st = State({"topic": {"chat": -100, "thread": tid, "resume": None}})
    await msg_topic_name(msg2, ctx, user(42), st, cast(Bot, bot))  # type: ignore[arg-type]
    assert bot.renamed == [(-100, tid, "Log")] and "«Study log» → «Log»" in sink.out[-1][0]
    # too short / too long names are refused without clearing the state
    bad = pmsg("x" * 129)
    sink = Sink()
    object.__setattr__(bad, "answer", sink)
    st = State({"topic": {"chat": -100, "thread": 0, "resume": None}})
    await msg_topic_name(bad, ctx, user(42), st, cast(Bot, bot))  # type: ignore[arg-type]
    assert not st.cleared and "1–128" in sink.out[-1][0]
    # subjects subscription via the chat card is per user, shared route
    from wklabs.bot.callbacks import ChatCb

    object.__setattr__(msg, "edit_text", Sink())  # screens edit in place

    class Cb:
        def __init__(self):
            self.message = msg
            self.alerts: list[str] = []

        async def answer(self, text=None, show_alert=False):
            if text:
                self.alerts.append(text)

    cb = Cb()
    await cb_global_toggle(cb, ChatCb(chat=-100, action="subj"), ctx, user(42), cast(Bot, bot))  # type: ignore[arg-type]
    r = next(x for x in await ctx.routes.for_chat(-100) if x.category == "subjects")
    assert r.subscribers == [42] and r.enabled
    await ctx.chats.add_member(-100, 7, "message")
    await cb_global_toggle(cb, ChatCb(chat=-100, action="subj"), ctx, user(7), cast(Bot, bot))  # type: ignore[arg-type]
    r = next(x for x in await ctx.routes.for_chat(-100) if x.category == "subjects")
    assert r.subscribers == [42, 7] and len(await ctx.routes.for_chat(-100)) == 1
    await cb_global_toggle(cb, ChatCb(chat=-100, action="subj"), ctx, user(42), cast(Bot, bot))  # type: ignore[arg-type]
    await cb_global_toggle(cb, ChatCb(chat=-100, action="subj"), ctx, user(7), cast(Bot, bot))  # type: ignore[arg-type]
    assert await ctx.routes.for_chat(-100) == []  # nobody left → off
    # system is admins only
    await cb_global_toggle(cb, ChatCb(chat=-100, action="sys"), ctx, user(42), cast(Bot, bot))  # type: ignore[arg-type]
    assert cb.alerts[-1] == "not allowed for this route"
    assert me_member().status == "member" and BOT_ID
