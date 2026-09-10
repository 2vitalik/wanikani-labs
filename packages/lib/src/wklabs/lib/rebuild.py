"""Rebuild `events` from `history` (authoritative replay).

Used after importing old snapshots or after changing the event taxonomy.
Old events are dropped; rebuilt ones are marked notified (no re-sending).
"""

from __future__ import annotations

import logging
from typing import Any

from pymongo.errors import BulkWriteError

from .db import Db
from .events import derive_events
from .timeutil import utcnow

log = logging.getLogger(__name__)

Json = dict[str, Any]


async def rebuild_events(db: Db, *, batch: int = 2000) -> dict[str, int]:
    started = utcnow()
    await db.events.delete_many({})
    counts = {"history": 0, "events": 0}
    buf: list[Json] = []
    prev_key: tuple[Any, ...] | None = None
    prev_item: Json | None = None

    async def flush() -> None:
        if not buf:
            return
        try:
            await db.events.insert_many(buf, ordered=False)
        except BulkWriteError as exc:
            log.warning("rebuild: %d duplicates", len(exc.details.get("writeErrors", [])))
        counts["events"] += len(buf)
        buf.clear()

    cursor = db.history.find(
        {}, sort=[("resource", 1), ("account", 1), ("resource_id", 1), ("data_updated_at", 1)]
    )
    async for h in cursor:
        counts["history"] += 1
        key = (h["resource"], h.get("account"), h["resource_id"])
        if key != prev_key:
            prev_key, prev_item = key, None
        events = derive_events(
            h["resource"],
            h.get("account"),
            prev_item,
            h["item"],
            first_seen_counts=(h.get("run_kind") == "incremental"),
        )
        for ev in events:
            d = ev.to_doc()
            d.update(
                {
                    "history_id": h["_id"],
                    "run_id": h.get("run_id"),
                    "fetched_at": h.get("fetched_at"),
                    "notified_at": started,
                    "rebuilt_at": started,
                }
            )
            buf.append(d)
        prev_item = h["item"]
        if len(buf) >= batch:
            await flush()
    await flush()
    log.info(
        "rebuild: %d history docs -> %d events in %.0fs",
        counts["history"],
        counts["events"],
        (utcnow() - started).total_seconds(),
    )
    return counts
