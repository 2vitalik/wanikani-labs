"""Session pass end to end: live message → edits → final summary; min_items; ⏹; /progress."""

from datetime import UTC, datetime, timedelta
from typing import cast
from zoneinfo import ZoneInfo

import pytest
from aiogram import Bot
from bson import ObjectId

from wklabs.bot.callbacks import ProgressCb, SessionCb
from wklabs.bot.handlers.progress import day_start, progress_screen, user_opts
from wklabs.bot.keyboards import kb_progress, kb_session
from wklabs.bot.render.common import tg_len
from wklabs.bot.render.progress import bar, render_map
from wklabs.bot.render.session import SessionView, render_session
from wklabs.lib.notify_settings import effective
from wklabs.lib.progress import LOCKED, normalize_options
from wklabs.lib.sessions import BY_USER, Session
from wklabs.lib.stats import window_stats
from wklabs.lib.users import TgUser

from .helpers import FakeBot, ident, make_ctx

T0 = datetime(2026, 9, 13, 14, 52, tzinfo=UTC)  # 17:52 Kyiv
TZ = ZoneInfo("Europe/Kyiv")
SUBJECTS = {
    1: {
        "_id": 1,
        "type": "kanji",
        "level": 12,
        "characters": "漢",
        "hidden_at": None,
        "item": {"data": {"meanings": [{"meaning": "Chinese", "primary": True}]}},
    },
    2: {
        "_id": 2,
        "type": "vocabulary",
        "level": 5,
        "characters": "語",
        "hidden_at": None,
        "item": {"data": {"meanings": [{"meaning": "language", "primary": True}]}},
    },
    3: {
        "_id": 3,
        "type": "radical",
        "level": 1,
        "characters": "一",
        "hidden_at": None,
        "item": {"data": {"meanings": [{"meaning": "ground", "primary": True}]}},
    },
}


def m(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


NOW = m(180)  # frozen "now": inside the 24 h lookback, before assignment 2 is due


@pytest.fixture(autouse=True)
def _freeze_now(monkeypatch: pytest.MonkeyPatch) -> None:
    for target in (
        "wklabs.lib.sessions.utcnow",
        "wklabs.bot.notifier.utcnow",
        "wklabs.bot.handlers.progress.utcnow",
    ):
        monkeypatch.setattr(target, lambda: NOW)


def ev(kind: str, sid: int | None, at: datetime, key: str = "07fff792", **meta) -> dict:
    return {
        "kind": kind,
        "at": at,
        "account": key,
        "subject_id": sid,
        "subject_type": SUBJECTS[sid]["type"] if sid in SUBJECTS else None,
        "meta": meta,
        "history_id": ObjectId(),
        "notified_at": at,  # not for the instant pass
    }


def reviewed(sid: int, at: datetime, correct: bool = True, key: str = "07fff792") -> dict:
    return ev(
        "reviewed",
        sid,
        at,
        key,
        count=1,
        correct=correct,
        meaning_wrong=0 if correct else 1,
        reading_wrong=0,
    )


def test_render_session_and_map():
    events = [
        reviewed(1, m(0)),
        ev("srs_up", 1, m(0), from_stage=4, to_stage=5),
        ev("passed", 1, m(0)),
        reviewed(2, m(3), correct=False),
        ev("srs_down", 2, m(3), from_stage=6, to_stage=4),
        ev("started", 3, m(13)),
        ev("srs_up", 3, m(13), from_stage=0, to_stage=1),
    ]
    st = window_stats(events, SUBJECTS)
    s = Session(ObjectId(), "07fff792", 15, m(0), m(13), 3)
    after = {
        (12, "kanji", 5): 1,
        (5, "vocabulary", 4): 1,
        (1, "radical", 1): 1,
        (1, "radical", LOCKED): 2,
    }
    before = {
        (12, "kanji", 4): 1,
        (5, "vocabulary", 6): 1,
        (1, "radical", 0): 1,
        (1, "radical", LOCKED): 2,
    }
    view = SessionView("Vitalik", s, st, SUBJECTS, TZ, due=40, level=12, after=after, before=before)
    text = render_session(view, {"items": "wrong", "changes": True, "lessons": True, "wins": True})[
        0
    ]
    assert text.startswith("🧘 <b>Vitalik</b> · session 17:52–18:05 (13 min)")
    assert "2 reviews · ✅ 1 ❌ 1 · 50% (answers 80%) · 0.2/min" in text
    assert "⬆️ 2 ⬇️ 1 · → Guru 1 · 📖 1 lessons" in text and "⏳ due 40" in text
    assert "🩷 apprentice 1 → 2" in text
    assert (
        "<blockquote expandable>❌ wrong (1)\n<code>💜2→🩷4</code> 🟣 L05 語 · language (m1)"
        in text
    )
    assert "💜 passed (Guru): 🔴 漢 · Chinese" in text and "📖 lessons: 🔵 一 · ground" in text
    assert "🗺 what changed\nL01 🤍 1→0 · 🩷 0→1\nL05 🩷 0→1 · 💜 1→0\nL12 🩷 1→0 · 💜 0→1" in text
    # live: no heavy blocks, "live" marker; counts only hides the lists; ⏹ mark when user-ended
    live = render_session(
        SessionView("Vitalik", s, st, SUBJECTS, TZ, live=True), {"items": "wrong"}
    )[0]
    assert "17:52 → … · live · 13 min" in live and "what changed" not in live and "❌ wrong" in live
    s.closed_by = BY_USER
    none = render_session(SessionView("V", s, st, SUBJECTS, TZ, preview=True), {"items": "none"})[0]
    assert "⏹" in none and "preview" in none and "blockquote" not in none
    full = render_session(SessionView("V", s, st, SUBJECTS, TZ), {"items": "all", "map": True})[0]
    assert "✅ correct (1)" in full and "🗺 map" not in full  # no matrix → no map block
    full = render_session(view, {"items": "all", "map": True, "map_levels": "all"})[0]
    assert "🗺 map\nL01 " in full
    # progress map rendering
    assert bar({"apprentice": 1, "burned": 3}) == "🩷🩷🩷🔥🔥🔥🔥🔥🔥🔥"
    assert bar({}) == "▫️" * 10 and len(bar({"locked": 1, "guru": 1, "burned": 1})) == 10
    opts = normalize_options({"style": "both", "sort": "desc"})
    text = render_map("Vitalik", 12, [1, 5, 12], after, before, opts, due=40, diff_title="session")
    lines = text.split("\n")
    assert lines[0] == "🗺 <b>Vitalik</b> · L12 · levels 1–12 ↓ · Δ session"
    assert lines[1].startswith("🔒 2 🩷 2 💜 1") and lines[1].endswith("⏳ due 40")
    # style both = bar line (current level in bold, no marker that shifts the bar) + counts line
    assert lines[3] == "<b>L12</b> 💜💜💜💜💜💜💜💜💜💜 · 🩷 1→0 · 💜 0→1"
    assert lines[4] == "<code>    🔒0 🩷0 💜1</code>"  # columns = groups present in shown levels
    assert lines[7] == "L01 🔒🔒🔒🔒🔒🔒🔒🩷🩷🩷 · 🤍 1→0 · 🩷 0→1"
    assert lines[-1] == "<i>filter: all · style: both</i>"
    counts = render_map("V", 12, [1, 5, 12], after, None, normalize_options({"style": "counts"}))
    assert (
        "\nL01 <code>🔒2 🩷1 💜0</code>\nL05 <code>🔒0 🩷1 💜0</code>\n<b>L12</b> <code>" in counts
    )
    stage = render_map("V", 12, [1, 5, 12], after, before, normalize_options({"group": "stage"}))
    assert "🩷 <b>Apprentice</b> 2 (+1): L01 0→1 · L05 0→1 · L12 1→0" in stage
    changed = render_map(
        "V", 12, [1, 5, 12], after, after, normalize_options({"filter": "changed"})
    )
    assert "nothing to show" in changed
    # keyboards and callback sizes
    kb = kb_progress("07fff792", opts, accounts=[], in_group=True)
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert labels[1] == "• now-5" and labels[-1] == "🧹 Close"
    assert len(SessionCb(id="0" * 24, action="end").pack().encode()) <= 64
    assert len(ProgressCb(key="07fff792", opt="levels").pack().encode()) <= 64
    labels = [b.text for row in kb_session(ObjectId(), live=True).inline_keyboard for b in row]
    assert labels == ["⏹ End now", "🗺 Progress"]
    assert (
        day_start(datetime(2026, 9, 14, 0, 30, tzinfo=UTC), TZ).day == 13
    )  # 03:30 Kyiv → yesterday 04:00
    assert day_start(datetime(2026, 9, 14, 2, 0, tzinfo=UTC), TZ).day == 14


async def _account(ctx, bot_chat: int = 42):
    acc = await ctx.accounts.create(ident(), "tok", owner_tg_id=bot_chat, source="test")
    await ctx.chats.ensure_private(bot_chat)
    routes = await ctx.routes.ensure_account_routes(acc.key, bot_chat, created_by=bot_chat)
    await ctx.db.col("subjects").insert_many([dict(d) for d in SUBJECTS.values()])
    await ctx.db.col("assignments").insert_many(
        [
            {
                "account": acc.key,
                "subject_id": 1,
                "srs_stage": 5,
                "hidden": False,
                "available_at": m(-60),
            },
            {
                "account": acc.key,
                "subject_id": 2,
                "srs_stage": 4,
                "hidden": False,
                "available_at": m(600),
            },
        ]
    )
    await ctx.db.current("user").insert_one({"_id": acc.key, "level": 12})
    return acc, next(r for r in routes if r.kind == "session")


async def _polled(ctx, key: str, at: datetime) -> None:
    for res in ("review_statistics", "assignments"):
        await ctx.db.sync_state.update_one(
            {"_id": f"{key}:{res}"}, {"$set": {"last_ok_at": at}}, upsert=True
        )


async def test_session_pass_live_edit_final(db):
    bot = FakeBot()
    ctx = make_ctx(db, bot=bot)
    acc, route = await _account(ctx)
    assert effective(route)["gap"] == 15 and effective(route)["live"] is True
    await db.events.insert_many(
        [reviewed(1, m(0)), ev("srs_up", 1, m(0), from_stage=4, to_stage=5), reviewed(2, m(1))]
    )
    await _polled(ctx, acc.key, m(2))
    assert await ctx.notifier.notify_sessions() == 1  # live message posted
    assert len(bot.sent) == 1 and "live" in bot.sent[0][2] and "2 reviews" in bot.sent[0][2]
    rep = await ctx.reports.get(route.id, (await ctx.sessions.current(acc.key, 15)).key)  # type: ignore[union-attr]
    assert rep and rep.message_ids == [1] and not rep.final
    assert await ctx.notifier.notify_sessions() == 0  # nothing new: no edit either
    await db.events.insert_many([reviewed(3, m(5), correct=False)])
    await _polled(ctx, acc.key, m(6))
    assert await ctx.notifier.notify_sessions() == 1  # edited in place, not re-sent
    assert len(bot.sent) == 1 and len(bot.edited) == 1 and "3 reviews" in bot.edited[0][2]
    # a poll 15 min after the last instant closes it → final edit, session reported
    await _polled(ctx, acc.key, m(21))
    assert await ctx.notifier.notify_sessions() == 1
    assert len(bot.edited) == 2 and "14:52" not in bot.edited[1][2]
    final = bot.edited[1][2]
    assert "17:52–17:57 (5 min)" in final and "what changed" in final and "live" not in final
    s = (await ctx.sessions.recent(acc.key, 15))[0]
    assert s.reported_at and s.delivered == [route.id] and s.stats and s.stats["n_items"] == 3
    rep = await ctx.reports.get(route.id, s.key)
    assert rep and rep.final and rep.message_ids == [1]
    assert await ctx.notifier.notify_sessions() == 0
    # a tiny session (below min_items 3) closes silently; a live message would still be finalized
    await db.events.insert_many([reviewed(1, m(60))])
    await _polled(ctx, acc.key, m(61))
    await ctx.routes.set_setting(route.id, "live", False, by=42)
    assert await ctx.notifier.notify_sessions() == 0
    await _polled(ctx, acc.key, m(80))
    assert await ctx.notifier.notify_sessions() == 0
    s2 = (await ctx.sessions.recent(acc.key, 15))[0]
    assert s2.reported_at and s2.delivered == [route.id] and len(bot.sent) == 1
    # preview renders the last closed session with the route's settings
    assert await ctx.notifier.preview_session(route) is None
    assert "preview" in bot.sent[-1][2]
    # the live message was deleted by a human → the final summary is sent anew
    await db.events.insert_many([reviewed(1, m(100)), reviewed(2, m(101)), reviewed(3, m(102))])
    await ctx.routes.set_setting(route.id, "live", True, by=42)
    await _polled(ctx, acc.key, m(103))
    await ctx.notifier.notify_sessions()
    live_id = bot.sent[-1]
    bot.gone.add(len(bot.sent))
    await _polled(ctx, acc.key, m(130))
    await ctx.notifier.notify_sessions()
    assert (
        bot.sent[-1] != live_id
        and "17:52" not in bot.sent[-1][2]
        and "3 reviews" in bot.sent[-1][2]
    )


async def test_session_dry_run_and_two_gaps(db):
    ctx = make_ctx(db)  # no bot → dry-run: sessions still tracked, reports without message ids
    acc, route = await _account(ctx)
    twin = await ctx.routes.add_target(acc.key, "session", 42, None, None, by=42)
    await ctx.routes.set_setting(twin.id, "gap", 30, by=42)
    await db.events.insert_many([reviewed(1, m(0)), reviewed(2, m(20)), reviewed(3, m(21))])
    await _polled(ctx, acc.key, m(22))
    await ctx.notifier.notify_sessions()
    assert await ctx.sessions.current(acc.key, 15) is not None  # 0 → 20 split for gap 15
    assert (await ctx.sessions.current(acc.key, 30)).n_instants == 3  # type: ignore[union-attr]
    first = (await ctx.sessions.recent(acc.key, 15))[0]
    assert first.reported_at and first.delivered == [route.id] and first.n_instants == 1
    rep = await ctx.reports.get(route.id, first.key)
    assert rep is None  # below min_items: nothing rendered
    live = await ctx.reports.get(twin.id, (await ctx.sessions.current(acc.key, 30)).key)  # type: ignore[union-attr]
    assert live and live.dry_run and live.message_ids == []


async def test_progress_screen_and_prefs(db):
    bot = FakeBot()
    ctx = make_ctx(db, bot=bot)
    acc, _route = await _account(ctx)
    await db.events.insert_many(
        [reviewed(1, m(0)), ev("srs_up", 1, m(0), from_stage=4, to_stage=5)]
    )
    await _polled(ctx, acc.key, m(1))
    await ctx.notifier.notify_sessions()
    user = TgUser(42, "v", "V", "en", "user", "active", m(0), m(0))
    opts = user_opts(user, acc.key)
    text, kb = await progress_screen(ctx, user, acc, opts, in_group=False)
    assert text.startswith("🗺 <b>Vitalik</b> · L12 · levels 12–12 ↑ · Δ session 17:52")
    assert "<b>L12</b> 💜💜💜💜💜💜💜💜💜💜 · 🩷 1→0 · 💜 0→1" in text and "⏳ due 1" in text
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert labels[:5] == ["now-3", "• now-5", "now-10", "1…now", "all"] and "🧹 Close" not in labels
    assert labels[5:11] == [
        "sort: ↑",
        "group: level",
        "filter: all",
        "style: emoji",
        "Δ: session",
        "🔄",
    ]
    opts["levels"], opts["diff"] = "all", "week"
    text, _ = await progress_screen(ctx, user, acc, opts, in_group=True)
    assert "levels 1–12" in text and "Δ 7 days" in text
    await ctx.users.ensure(42)
    await ctx.users.set_pref(42, f"progress.{acc.key}.sort", "desc")
    fresh = await ctx.users.get(42)
    assert fresh and user_opts(fresh, acc.key)["sort"] == "desc"
    assert cast(Bot, bot) is not None


def test_map_trims_to_the_telegram_limit():
    after = {
        (lvl, "vocabulary", st): 100 for lvl in range(1, 61) for st in (LOCKED, 0, 1, 5, 7, 8, 9)
    }
    levels = list(range(1, 61))
    text = render_map("V", 60, levels, after, None, normalize_options({"style": "both"}))
    assert tg_len(text) <= 4096 and "levels don't fit" in text
    assert "<b>L60</b>" in text and "\nL01 " not in text  # ascending: far (low) levels go first
    text = render_map("V", 60, levels, after, None, normalize_options({"style": "emoji"}))
    assert "don't fit" not in text and "\nL01 " in text  # 60 bars fit as they are
