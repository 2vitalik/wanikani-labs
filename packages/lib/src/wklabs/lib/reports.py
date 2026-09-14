"""Sent reports (session summaries, later daily/weekly): one message per (route, key).

Generalizes `events.delivered` for non-instant notifications: a restart in the
middle finds the report by key and *edits* the message instead of sending it
again; `text_hash` skips edits that would not change anything (T32 §3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from .db import Db
from .timeutil import utcnow

Json = dict[str, Any]


def text_hash(texts: list[str]) -> str:
    return sha1("\x00".join(texts).encode()).hexdigest()[:16]


@dataclass(slots=True)
class Report:
    id: ObjectId
    route_id: ObjectId
    key: str
    chat_id: int
    thread_id: int | None
    message_ids: list[int]
    final: bool
    text_hash: str
    sent_at: datetime
    updated_at: datetime
    dry_run: bool = False

    @classmethod
    def from_doc(cls, d: Json) -> Report:
        return cls(
            id=d["_id"],
            route_id=d["route_id"],
            key=str(d["key"]),
            chat_id=int(d["chat_id"]),
            thread_id=d.get("thread_id"),
            message_ids=[int(x) for x in d.get("message_ids") or []],
            final=bool(d.get("final")),
            text_hash=str(d.get("text_hash") or ""),
            sent_at=d.get("sent_at") or utcnow(),
            updated_at=d.get("updated_at") or utcnow(),
            dry_run=bool(d.get("dry_run")),
        )

    @property
    def message_id(self) -> int | None:
        return self.message_ids[0] if self.message_ids else None


class ReportRepo:
    def __init__(self, db: Db) -> None:
        self.db = db

    async def get(self, route_id: ObjectId, key: str) -> Report | None:
        d = await self.db.reports.find_one({"route_id": route_id, "key": key})
        return Report.from_doc(d) if d else None

    async def upsert(
        self,
        route_id: ObjectId,
        key: str,
        *,
        chat_id: int,
        thread_id: int | None,
        message_ids: list[int],
        final: bool,
        text_hash: str,
        dry_run: bool = False,
    ) -> Report:
        now = utcnow()
        d = await self.db.reports.find_one_and_update(
            {"route_id": route_id, "key": key},
            {
                "$set": {
                    "chat_id": chat_id,
                    "thread_id": thread_id,
                    "message_ids": message_ids,
                    "final": final,
                    "text_hash": text_hash,
                    "dry_run": dry_run,
                    "updated_at": now,
                },
                "$setOnInsert": {"sent_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        assert d is not None
        return Report.from_doc(d)

    async def for_key(self, key: str) -> list[Report]:
        return [Report.from_doc(d) async for d in self.db.reports.find({"key": key})]
