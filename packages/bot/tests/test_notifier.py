from datetime import UTC, datetime

from wklabs.lib.chats import ADMIN, KICKED, Inspection, Rights
from wklabs.lib.delivery import (
    ERR_TOPIC_CLOSED,
    ERR_TOPIC_DELETED,
    PRESET_PER_ACCOUNT,
    PRESET_PER_CATEGORY,
)

from .helpers import FakeBot, bad_request, forbidden, ident, make_ctx

FORUM = Inspection(
    type="supergroup",
    title="WK",
    is_forum=True,
    status=ADMIN,
    rights=Rights(can_post=True, can_manage_topics=True),
)

AT = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


async def _seed(db, key: str, hid: int = 1) -> None:
    await db.col("subjects").replace_one(
        {"_id": 1},
        {
            "_id": 1,
            "type": "kanji",
            "level": 2,
            "characters": "火",
            "item": {"data": {"meanings": [{"meaning": "Fire", "primary": True}]}},
        },
        upsert=True,
    )
    await db.events.insert_many(
        [
            {
                "kind": "reviewed",
                "at": AT,
                "account": key,
                "subject_id": 1,
                "subject_type": "kanji",
                "meta": {"count": 1, "correct": True, "meaning_wrong": 0, "reading_wrong": 0},
                "history_id": hid,
                "notified_at": None,
            },
            {
                "kind": "hidden",
                "at": AT,
                "account": key,
                "subject_id": 1,
                "subject_type": "kanji",
                "meta": {},
                "history_id": hid + 1,
                "notified_at": None,
            },
        ]
    )


async def test_dry_run_private_route(db, caplog):
    ctx = make_ctx(db)
    acc = await ctx.accounts.create(ident(), "tok", owner_tg_id=42, source="test")
    await ctx.chats.ensure_private(42)
    await ctx.routes.ensure_account_routes(acc.key, 42, created_by=42)
    await _seed(db, acc.key)
    caplog.set_level("INFO")
    assert await ctx.notifier.notify_pending() == 0  # dry-run sends nothing
    assert await db.events.count_documents({"notified_at": None}) == 0
    hidden = await db.events.find_one({"kind": "hidden"})
    assert hidden and hidden.get("skipped") is True
    assert "dry-run → 42/None" in caplog.text and "火" in caplog.text
    assert "<b>Vitalik</b>" in caplog.text  # label, not key
    assert await ctx.notifier.notify_pending() == 0  # idempotent


async def test_no_route_is_skipped(db):
    ctx = make_ctx(db)
    acc = await ctx.accounts.create(ident(), "tok", owner_tg_id=42, source="test")
    await _seed(db, acc.key)
    assert await ctx.notifier.notify_pending() == 0
    ev = await db.events.find_one({"kind": "reviewed"})
    assert ev and ev["skipped"] is True and ev["no_route"] is True


async def test_preset_topics_and_delivery(db):
    bot = FakeBot()
    ctx = make_ctx(db, bot=bot)
    acc = await ctx.accounts.create(ident(), "tok", owner_tg_id=42, source="test")
    chat = await ctx.chats.apply_inspection(-100, FORUM)
    res = await ctx.topics.apply_preset(chat, [acc], PRESET_PER_CATEGORY, by=42)
    assert res.labels == ["Vitalik"] and res.created == [
        "📝 Vitalik · reviews",
        "🏆 Vitalik · milestones",
    ]
    assert bot.topics == [(-100, "📝 Vitalik · reviews"), (-100, "🏆 Vitalik · milestones")]
    routes = await ctx.routes.for_account(acc.key)
    assert [(r.category, r.thread_id) for r in routes] == [("milestones", 8), ("reviews", 7)]
    await _seed(db, acc.key)
    assert await ctx.notifier.notify_pending() == 1
    assert bot.sent[0][:2] == (-100, 7)
    ev = await db.events.find_one({"kind": "reviewed"})
    assert ev and ev["delivered"] == [routes[1].id] and ev["message_ids"] == [1]
    assert await db.tg_messages.count_documents({"chat_id": -100}) == 1
    assert await ctx.notifier.notify_pending() == 0
    # a route without a topic posts to General; nothing is created on delivery
    chat = await ctx.chats.get(-100)
    assert chat and len(chat.topics) == 2 and chat.preset == PRESET_PER_CATEGORY
    # per-account preset: one new topic, shared by both categories
    res = await ctx.topics.apply_preset(chat, [acc], PRESET_PER_ACCOUNT, by=42)
    assert res.created == ["Vitalik"] and res.reused == 1
    routes = await ctx.routes.for_account(acc.key)
    assert {r.thread_id for r in routes} == {9}
    # second time: found by name
    chat = await ctx.chats.get(-100)
    assert chat is not None
    res = await ctx.topics.apply_preset(chat, [acc], PRESET_PER_ACCOUNT, by=42)
    assert res.created == [] and res.reused == 2
    # renaming the account renames only the bot's untouched topics that carry the label
    await ctx.chats.remember_topic(-100, 7, "My reviews")  # human renamed this one
    assert await ctx.topics.rename_account(acc.key, "Vitalik", "Vit") == 1
    assert bot.renamed == [(-100, 9, "Vit")]
    r = (await ctx.routes.for_account(acc.key))[0]
    assert r.thread_title == "Vit"


async def test_route_health_topic_deleted_and_forbidden(db):
    bot = FakeBot()
    ctx = make_ctx(db, bot=bot)
    acc = await ctx.accounts.create(ident(), "tok", owner_tg_id=42, source="test")
    chat = await ctx.chats.apply_inspection(-100, FORUM)
    await ctx.topics.apply_preset(chat, [acc], PRESET_PER_CATEGORY, by=42)
    await _seed(db, acc.key)
    bot.fail[-100] = bad_request(-100, "message thread not found")
    assert await ctx.notifier.notify_pending() == 0
    r = next(x for x in await ctx.routes.for_account(acc.key) if x.category == "reviews")
    assert r.thread_id is None and r.error == ERR_TOPIC_DELETED and r.has_error
    assert r.thread_title == "📝 Vitalik · reviews"  # kept for ✨ Recreate
    chat = await ctx.chats.get(-100)
    assert chat and 7 not in chat.topics
    dm = [m for m in bot.sent if m[0] == 42]
    assert len(dm) == 1 and "topic deleted" in dm[0][2]
    # the event is marked notified (not resent forever); the owner was told once
    assert await db.events.count_documents({"notified_at": None}) == 0
    # recreate brings the topic back under its old name and clears the error
    del bot.fail[-100]
    topic = await ctx.topics.recreate(r)
    assert topic and topic.name == "📝 Vitalik · reviews" and bot.topics[-1][1] == topic.name
    r2 = await ctx.routes.get(r.id)
    assert r2 and r2.thread_id == topic.thread_id and not r2.has_error
    # closed topic → error once, DM once
    bot.fail[-100] = bad_request(-100, "TOPIC_CLOSED")
    await _seed(db, acc.key, hid=3)
    await ctx.notifier.notify_pending()
    r3 = await ctx.routes.get(r.id)
    assert r3 and r3.error == ERR_TOPIC_CLOSED
    chat = await ctx.chats.get(-100)
    assert chat and chat.topics[topic.thread_id].closed
    assert len([m for m in bot.sent if m[0] == 42]) == 2
    # kicked → every route in the chat off, chat marked, owner told
    bot.fail[-100] = forbidden(-100)
    await _seed(db, acc.key, hid=5)
    await ctx.notifier.notify_pending()
    assert await ctx.routes.for_chat(-100) == []
    chat = await ctx.chats.get(-100)
    assert chat and chat.status == KICKED and not chat.present
    assert "Removed from" in bot.sent[-1][2]


async def test_system_falls_back_to_admin_dm(db):
    bot = FakeBot()
    ctx = make_ctx(db, bot=bot, admin_ids=[1])
    await ctx.notifier.system("hello")
    assert bot.sent == [(1, None, "🛠 hello")]
    await ctx.routes.upsert(None, "system", -100, created_by=1)
    await ctx.chats.seen(-100, type="supergroup", title="WK")
    await ctx.notifier.system("again")
    assert bot.sent[-1] == (-100, None, "🛠 again")
