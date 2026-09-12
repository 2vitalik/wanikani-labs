from datetime import UTC, datetime

from wklabs.lib.delivery import LAYOUT_TOPICS

from .helpers import FakeBot, ident, make_ctx

AT = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


async def _seed(db, key: str) -> None:
    await db.col("subjects").insert_one(
        {
            "_id": 1,
            "type": "kanji",
            "level": 2,
            "characters": "火",
            "item": {"data": {"meanings": [{"meaning": "Fire", "primary": True}]}},
        }
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
                "history_id": 1,
                "notified_at": None,
            },
            {
                "kind": "hidden",
                "at": AT,
                "account": key,
                "subject_id": 1,
                "subject_type": "kanji",
                "meta": {},
                "history_id": 2,
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


async def test_forum_topic_created_on_first_delivery(db):
    bot = FakeBot()
    ctx = make_ctx(db, bot=bot)
    acc = await ctx.accounts.create(ident(), "tok", owner_tg_id=42, source="test")
    await ctx.chats.upsert(
        -100,
        type="supergroup",
        title="WK",
        is_forum=True,
        layout=LAYOUT_TOPICS,
        set_up_by=42,
        bot_is_admin=True,
        can_manage_topics=True,
    )
    routes = await ctx.routes.move_account(acc.key, -100, created_by=42)
    await _seed(db, acc.key)
    assert await ctx.notifier.notify_pending() == 1
    assert bot.topics == [(-100, "📝 Vitalik · reviews")]
    assert bot.sent[0][:2] == (-100, 7)
    r = await ctx.routes.get(routes[0].id)
    assert r and r.thread_id == 7 and r.thread_title == "📝 Vitalik · reviews"
    ev = await db.events.find_one({"kind": "reviewed"})
    assert ev and ev["delivered"] == [routes[0].id] and ev["message_ids"] == [1]
    assert await db.tg_messages.count_documents({"chat_id": -100}) == 1
    assert await ctx.notifier.notify_pending() == 0
    # renaming the account renames its topics
    await ctx.topics.rename_account(acc.key, "Vit")
    assert bot.renamed == [(-100, 7, "📝 Vit · reviews")]


async def test_system_falls_back_to_admin_dm(db):
    bot = FakeBot()
    ctx = make_ctx(db, bot=bot, admin_ids=[1])
    await ctx.notifier.system("hello")
    assert bot.sent == [(1, None, "🛠 hello")]
    await ctx.routes.upsert(None, "system", -100, created_by=1)
    await ctx.chats.upsert(-100, type="supergroup", title="WK", is_forum=False)
    await ctx.notifier.system("again")
    assert bot.sent[-1] == (-100, None, "🛠 again")
