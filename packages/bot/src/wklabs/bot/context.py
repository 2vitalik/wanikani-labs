"""Shared runtime objects for jobs and handlers."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from html import escape

from aiogram import Bot

from wklabs.lib.db import Db
from wklabs.lib.settings import Settings
from wklabs.lib.sync import SyncEngine, SyncResult
from wklabs.lib.timeutil import utcnow

from .notifier import Notifier
from .topics import TopicManager

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    settings: Settings
    db: Db
    engine: SyncEngine
    topics: TopicManager
    notifier: Notifier
    bot: Bot | None = None
    sync_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_result: SyncResult | None = None
    last_error_notified_at: datetime | None = None
    failing: bool = False
    started_at: datetime = field(default_factory=utcnow)

    async def run_sync(
        self, *, full: bool = False, include_global: bool = False, include_accounts: bool = True
    ) -> SyncResult:
        """Sync + deliver digests; serialized; system-topic alerts on errors/recovery."""
        async with self.sync_lock:
            res = await self.engine.run(
                full=full, include_global=include_global, include_accounts=include_accounts
            )
            self.last_result = res
            try:
                sent = await self.notifier.notify_pending()
                if sent:
                    log.info("delivered %d digest message(s)", sent)
            except Exception:
                log.exception("notify failed")
            await self._alerts(res)
            return res

    async def _alerts(self, res: SyncResult) -> None:
        now = utcnow()
        if res.errors:
            since = (
                (now - self.last_error_notified_at).total_seconds()
                if self.last_error_notified_at
                else None
            )
            if since is None or since > 1800:
                errs = "\n".join(f"• {escape(e)}" for e in res.errors[:10])
                await self.notifier.system(f"❌ sync errors ({res.kind}):\n{errs}")
                self.last_error_notified_at = now
            self.failing = True
        elif self.failing:
            self.failing = False
            await self.notifier.system("✅ sync recovered")
