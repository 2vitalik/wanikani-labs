"""APScheduler jobs: account poll, global poll (subjects…), daily heartbeat."""

from __future__ import annotations

import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from wklabs.lib.timeutil import utcnow

from .context import AppContext
from .status_text import heartbeat_text

log = logging.getLogger(__name__)


async def job_sync_accounts(ctx: AppContext) -> None:
    await ctx.run_sync(include_global=False, include_accounts=True)


async def job_sync_global(ctx: AppContext) -> None:
    await ctx.run_sync(include_global=True, include_accounts=False)


async def job_heartbeat(ctx: AppContext) -> None:
    text = await heartbeat_text(ctx)
    await ctx.notifier.system(text)


def build_scheduler(ctx: AppContext) -> AsyncIOScheduler:
    s = ctx.settings
    tz = ZoneInfo(s.tz)
    sched = AsyncIOScheduler(
        timezone=tz, job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 120}
    )
    now = utcnow()
    # global first (subjects needed for labels), accounts a bit later
    sched.add_job(
        job_sync_global,
        IntervalTrigger(seconds=s.subjects_interval),
        args=[ctx],
        id="sync_global",
        next_run_time=now + timedelta(seconds=2),
    )
    sched.add_job(
        job_sync_accounts,
        IntervalTrigger(seconds=s.sync_interval),
        args=[ctx],
        id="sync_accounts",
        next_run_time=now + timedelta(seconds=20),
    )
    if s.heartbeat_time:
        hh, _, mm = s.heartbeat_time.partition(":")
        sched.add_job(
            job_heartbeat,
            CronTrigger(hour=int(hh), minute=int(mm or 0), timezone=tz),
            args=[ctx],
            id="heartbeat",
        )
    return sched
