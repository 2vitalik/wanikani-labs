"""/start text: works for anyone, tells the caller their id and admin status."""

from datetime import timedelta

from wklabs.bot.context import AppContext
from wklabs.bot.notifier import Notifier
from wklabs.bot.status_text import alive_text
from wklabs.bot.topics import TopicManager
from wklabs.lib.settings import Settings
from wklabs.lib.sync import SyncEngine
from wklabs.lib.timeutil import utcnow


def _ctx(db, admin_ids):
    settings = Settings(tg_admin_ids=admin_ids)
    topics = TopicManager(db, None, ["main"])
    return AppContext(
        settings=settings,
        db=db,
        engine=SyncEngine(db, {}),
        topics=topics,
        notifier=Notifier(db, None, topics, settings.tz, None),
    )


async def test_alive_text_non_admin_and_admin(db):
    ctx = _ctx(db, [])
    text = await alive_text(ctx, 42)
    assert "alive" in text and "no sync runs yet" in text
    assert "<code>42</code>" in text and "not in TG_ADMIN_IDS" in text

    await db.sync_runs.insert_one(
        {"started_at": utcnow() - timedelta(minutes=7), "kind": "incremental", "ok": True}
    )
    text = await alive_text(_ctx(db, [42]), 42)
    assert "(7 min ago) ✅" in text and "admin — /status" in text
    assert "not in TG_ADMIN_IDS" not in text
