"""/ping and /status texts over the repo-based context."""

from datetime import timedelta

from wklabs.bot.status_text import alive_text, status_text
from wklabs.lib.timeutil import utcnow

from .helpers import ident, make_ctx


async def test_alive_text(db):
    ctx = make_ctx(db, admin_ids=[42])
    text = await alive_text(ctx, 7)
    assert "alive" in text and "no sync runs yet" in text and "<code>7</code>" in text
    assert "admin" not in text and "dry-run" in text
    await db.sync_runs.insert_one(
        {"started_at": utcnow() - timedelta(minutes=7), "kind": "incremental", "ok": True}
    )
    text = await alive_text(ctx, 42, -1001234, 9)
    assert "(7 min ago) ✅" in text and "<code>42</code> · admin" in text
    assert "chat id: <code>-1001234</code> · thread 9" in text


async def test_status_text_lists_accounts(db):
    ctx = make_ctx(db, admin_ids=[42])
    text = await status_text(ctx, [], admin=False)
    assert "no accounts yet" in text and "db:" not in text
    acc = await ctx.accounts.create(ident(), "tok", owner_tg_id=42, source="test")
    text = await status_text(ctx, [acc], admin=True)
    assert "🟢 <b>Vitalik</b>" in text and "db: subjects" in text
