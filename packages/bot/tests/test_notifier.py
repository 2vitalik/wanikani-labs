from datetime import UTC, datetime

from wklabs.bot.notifier import Notifier
from wklabs.bot.topics import TopicManager


async def test_dry_run_marks_events_notified(db, caplog):
    await db.col("subjects").insert_one(
        {
            "_id": 1,
            "type": "kanji",
            "level": 2,
            "characters": "火",
            "item": {"data": {"meanings": [{"meaning": "Fire", "primary": True}]}},
        }
    )
    at = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
    await db.events.insert_many(
        [
            {
                "kind": "reviewed",
                "at": at,
                "account": "main",
                "subject_id": 1,
                "subject_type": "kanji",
                "meta": {"count": 1, "correct": True, "meaning_wrong": 0, "reading_wrong": 0},
                "history_id": 1,
                "notified_at": None,
            },
            {
                "kind": "hidden",
                "at": at,
                "account": "main",
                "subject_id": 1,
                "subject_type": "kanji",
                "meta": {},
                "history_id": 2,
                "notified_at": None,
            },
        ]
    )
    topics = TopicManager(db, None, ["main"])
    n = Notifier(db, None, topics, "Europe/Kyiv", None)
    caplog.set_level("INFO")
    assert await n.notify_pending() == 0  # dry-run sends nothing
    assert await db.events.count_documents({"notified_at": None}) == 0
    hidden = await db.events.find_one({"kind": "hidden"})
    assert hidden and hidden.get("skipped") is True
    assert "dry-run → main.reviews" in caplog.text and "火" in caplog.text
    assert await n.notify_pending() == 0  # idempotent
