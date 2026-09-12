"""Text blocks for /start, /status and the daily heartbeat (Telegram HTML)."""

from __future__ import annotations

from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from wklabs.lib.accounts import Account
from wklabs.lib.status import account_status, stage_buckets, sync_status
from wklabs.lib.timeutil import utcnow

from .context import AppContext


def _fmt_dt(dt: datetime | None, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%d.%m %H:%M") if dt else "—"


async def _account_block(ctx: AppContext, acc: Account, tz: ZoneInfo) -> list[str]:
    a = await account_status(ctx.db, acc.key)
    b = stage_buckets(a["stages"])
    return [
        f"{acc.emoji} <b>{escape(acc.label)}</b> · {escape(str(a['username']))} · "
        f"level {a['level']}" + (f" · <i>{escape(acc.status)}</i>" if not acc.is_active else ""),
        f"  reviews now <b>{a['reviews_now']}</b> · lessons {a['lessons_now']} · "
        f"next {_fmt_dt(a['next_reviews_at'], tz)} · 24h reviews {a['reviews_24h']}",
        "  " + " · ".join(f"{k[:3]} {v}" for k, v in b.items()),
    ]


async def status_text(ctx: AppContext, accounts: list[Account], *, admin: bool) -> str:
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
        if admin and last.get("errors"):
            lines.append("❌ " + escape("; ".join(last["errors"][:3])))
    else:
        lines.append("no sync runs yet")
    if admin:
        c = s["counts"]
        lines.append(
            f"db: subjects {c['subjects']} · assignments {c['assignments']} · "
            f"history {c['history']} · events {c['events']} (pending {c['pending_events']})"
        )
    if not accounts:
        lines.append("")
        lines.append("no accounts yet — /accounts to add one")
    for acc in accounts:
        lines.append("")
        lines.extend(await _account_block(ctx, acc, tz))
    up = utcnow() - ctx.started_at
    lines.append("")
    lines.append(
        f"uptime {timedelta(seconds=int(up.total_seconds()))!s} · "
        f"poll every {ctx.settings.sync_interval}s"
        + (" · <i>dry-run</i>" if ctx.notifier.dry_run else "")
    )
    return "\n".join(lines)


async def alive_text(
    ctx: AppContext, user_id: int | None, chat_id: int | None = None, thread_id: int | None = None
) -> str:
    """/ping — proves the bot is alive; shows the ids useful for the env and debugging."""
    tz = ZoneInfo(ctx.settings.tz)
    last = await ctx.db.sync_runs.find_one({}, sort=[("started_at", -1)])
    if last:
        age = int((utcnow() - last["started_at"]).total_seconds() // 60)
        ok = "✅" if last["ok"] else "❌"
        sync = f"last sync {_fmt_dt(last['started_at'], tz)} ({age} min ago) {ok}"
    else:
        sync = "no sync runs yet"
    up = timedelta(seconds=int((utcnow() - ctx.started_at).total_seconds()))
    lines = [
        f"👋 <b>wanikani-labs</b> alive · uptime {up!s} · poll every {ctx.settings.sync_interval}s",
        sync,
        f"your id: <code>{user_id}</code>"
        + (" · admin" if ctx.is_admin(user_id) else "")
        + (" · <i>dry-run, no Telegram delivery</i>" if ctx.notifier.dry_run else ""),
    ]
    if chat_id is not None and chat_id != user_id:
        here = f"chat id: <code>{chat_id}</code>"
        if thread_id is not None:
            here += f" · thread {thread_id}"
        lines.append(here)
    return "\n".join(lines)


async def heartbeat_text(ctx: AppContext) -> str:
    since = utcnow() - timedelta(hours=24)
    runs = await ctx.db.sync_runs.count_documents({"started_at": {"$gte": since}})
    failed = await ctx.db.sync_runs.count_documents({"started_at": {"$gte": since}, "ok": False})
    events = await ctx.db.events.count_documents({"at": {"$gte": since}})
    parts = [f"💓 24h: {runs} polls ({failed} failed) · {events} events"]
    for acc in await ctx.accounts.list(status=None):
        a = await account_status(ctx.db, acc.key)
        parts.append(
            f"{acc.emoji} {escape(acc.label)}: L{a['level']} · {a['reviews_24h']} reviews · "
            f"{a['reviews_now']} due now"
        )
    return "\n".join(parts)
