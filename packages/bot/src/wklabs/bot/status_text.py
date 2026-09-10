"""Text blocks for /start, /status and the daily heartbeat (Telegram HTML)."""

from __future__ import annotations

from datetime import timedelta
from html import escape
from zoneinfo import ZoneInfo

from wklabs.lib.status import account_status, stage_buckets, sync_status
from wklabs.lib.timeutil import utcnow

from .context import AppContext


def _fmt_dt(dt, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%d.%m %H:%M") if dt else "—"


async def status_text(ctx: AppContext) -> str:
    tz = ZoneInfo(ctx.settings.tz)
    s = await sync_status(ctx.db)
    last = s["last_run"]
    lines = ["<b>wanikani-labs</b>"]
    if last:
        age = utcnow() - last["started_at"]
        lines.append(
            f"last sync: {_fmt_dt(last['started_at'], tz)} "
            f"({int(age.total_seconds() // 60)} min ago) · {last['kind']} · "
            f"{'✅' if last['ok'] else '❌'} · events {last.get('events', 0)} · "
            f"req {last.get('requests', 0)}"
        )
        if last.get("errors"):
            lines.append("❌ " + escape("; ".join(last["errors"][:3])))
    else:
        lines.append("no sync runs yet")
    c = s["counts"]
    lines.append(
        f"db: subjects {c['subjects']} · assignments {c['assignments']} · "
        f"history {c['history']} · events {c['events']} (pending {c['pending_events']})"
    )
    for acc in ctx.settings.accounts:
        a = await account_status(ctx.db, acc)
        b = stage_buckets(a["stages"])
        lines.append("")
        lines.append(f"<b>{escape(acc)}</b> · {escape(str(a['username']))} · level {a['level']}")
        lines.append(
            f"  reviews now <b>{a['reviews_now']}</b> · lessons {a['lessons_now']} · "
            f"next {_fmt_dt(a['next_reviews_at'], tz)} · 24h reviews {a['reviews_24h']}"
        )
        lines.append("  " + " · ".join(f"{k[:3]} {v}" for k, v in b.items()))
    up = utcnow() - ctx.started_at
    lines.append("")
    lines.append(
        f"uptime {timedelta(seconds=int(up.total_seconds()))!s} · "
        f"poll every {ctx.settings.sync_interval}s"
        + (" · <i>dry-run</i>" if ctx.notifier.dry_run else "")
    )
    return "\n".join(lines)


async def alive_text(ctx: AppContext, user_id: int | None) -> str:
    """/start, /ping — for anyone: proves the bot is alive and shows the caller's id."""
    tz = ZoneInfo(ctx.settings.tz)
    last = await ctx.db.sync_runs.find_one({}, sort=[("started_at", -1)])
    if last:
        age = int((utcnow() - last["started_at"]).total_seconds() // 60)
        ok = "✅" if last["ok"] else "❌"
        sync = f"last sync {_fmt_dt(last['started_at'], tz)} ({age} min ago) {ok}"
    else:
        sync = "no sync runs yet"
    up = timedelta(seconds=int((utcnow() - ctx.started_at).total_seconds()))
    is_admin = user_id is not None and user_id in ctx.settings.tg_admin_ids
    lines = [
        f"👋 <b>wanikani-labs</b> alive · uptime {up!s} · poll every {ctx.settings.sync_interval}s",
        sync,
        f"your id: <code>{user_id}</code> · "
        + (
            "admin — /status /sync /help"
            if is_admin
            else "not in TG_ADMIN_IDS (admin commands ignored)"
        ),
    ]
    return "\n".join(lines)


async def heartbeat_text(ctx: AppContext) -> str:
    since = utcnow() - timedelta(hours=24)
    runs = await ctx.db.sync_runs.count_documents({"started_at": {"$gte": since}})
    failed = await ctx.db.sync_runs.count_documents({"started_at": {"$gte": since}, "ok": False})
    events = await ctx.db.events.count_documents({"at": {"$gte": since}})
    parts = [f"💓 24h: {runs} polls ({failed} failed) · {events} events"]
    for acc in ctx.settings.accounts:
        a = await account_status(ctx.db, acc)
        parts.append(
            f"{escape(acc)}: L{a['level']} · {a['reviews_24h']} reviews · "
            f"{a['reviews_now']} due now"
        )
    return "\n".join(parts)
