"""Status summary for `/status` (bot) and `wklabs status` (CLI)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .db import Db
from .resources import SRS_STAGES
from .timeutil import utcnow

Json = dict[str, Any]


async def account_status(db: Db, account: str) -> Json:
    user = await db.current("user").find_one({"_id": account})
    summary = await db.current("summary").find_one({"_id": account})
    stages: dict[int, int] = {}
    pipeline = [
        {"$match": {"account": account, "hidden": False}},
        {"$group": {"_id": "$srs_stage", "n": {"$sum": 1}}},
    ]
    async for row in await db.current("assignments").aggregate(pipeline):
        stages[int(row["_id"])] = int(row["n"])
    since = utcnow() - timedelta(hours=24)
    reviews_24h = 0
    async for row in await db.events.aggregate(
        [
            {"$match": {"account": account, "kind": "reviewed", "at": {"$gte": since}}},
            {"$group": {"_id": None, "n": {"$sum": "$meta.count"}}},
        ]
    ):
        reviews_24h = int(row["n"])
    return {
        "account": account,
        "username": (user or {}).get("username"),
        "level": (user or {}).get("level"),
        "reviews_now": (summary or {}).get("reviews_now"),
        "lessons_now": (summary or {}).get("lessons_now"),
        "next_reviews_at": (summary or {}).get("next_reviews_at"),
        "stages": stages,
        "reviews_24h": reviews_24h,
    }


async def sync_status(db: Db) -> Json:
    last = await db.sync_runs.find_one({}, sort=[("started_at", -1)])
    last_ok = await db.sync_runs.find_one({"ok": True}, sort=[("started_at", -1)])
    states: list[Json] = []
    async for s in db.sync_state.find({}, sort=[("_id", 1)]):
        states.append(s)
    counts = {
        "subjects": await db.current("subjects").estimated_document_count(),
        "assignments": await db.current("assignments").estimated_document_count(),
        "history": await db.history.estimated_document_count(),
        "events": await db.events.estimated_document_count(),
        "pending_events": await db.events.count_documents({"notified_at": None}),
    }
    return {"last_run": last, "last_ok_run": last_ok, "states": states, "counts": counts}


def stage_buckets(stages: dict[int, int]) -> dict[str, int]:
    b = {"Apprentice": 0, "Guru": 0, "Master": 0, "Enlightened": 0, "Burned": 0}
    for st, n in stages.items():
        name = SRS_STAGES.get(st, "")
        for key in b:
            if name.startswith(key):
                b[key] += n
    return b
