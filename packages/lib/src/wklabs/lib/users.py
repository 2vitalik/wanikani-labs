"""Telegram users: who talks to the bot, their role (admin/user) and access status."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pymongo import ReturnDocument

from .db import Db
from .timeutil import utcnow

log = logging.getLogger(__name__)
Json = dict[str, Any]

ADMIN, USER = "admin", "user"
PENDING, ACTIVE, BLOCKED = "pending", "active", "blocked"
STATUS_EMOJI = {ACTIVE: "✅", PENDING: "⏳", BLOCKED: "🚫"}


@dataclass(slots=True)
class TgUser:
    id: int
    username: str | None
    first_name: str | None
    lang: str | None
    role: str
    status: str
    created_at: datetime
    last_seen_at: datetime

    @classmethod
    def from_doc(cls, d: Json) -> TgUser:
        return cls(
            id=int(d["_id"]),
            username=d.get("username"),
            first_name=d.get("first_name"),
            lang=d.get("lang"),
            role=str(d.get("role") or USER),
            status=str(d.get("status") or PENDING),
            created_at=d.get("created_at") or utcnow(),
            last_seen_at=d.get("last_seen_at") or utcnow(),
        )

    @property
    def is_admin(self) -> bool:
        return self.role == ADMIN

    @property
    def is_active(self) -> bool:
        return self.status == ACTIVE

    @property
    def display(self) -> str:
        name = self.first_name or self.username or str(self.id)
        handle = f" @{self.username}" if self.username else ""
        return f"{name}{handle} · {self.id}"


class TgUserRepo:
    def __init__(self, db: Db, *, admin_ids: list[int], policy: str = "open") -> None:
        self.db = db
        self.admin_ids = set(admin_ids)
        self.policy = policy

    async def ensure(
        self,
        id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        lang: str | None = None,
    ) -> tuple[TgUser, bool]:
        """Upsert on every update; returns (user, is_new). Admins come from the env."""
        now = utcnow()
        role = ADMIN if id in self.admin_ids else USER
        initial = ACTIVE if role == ADMIN or self.policy == "open" else PENDING
        before = await self.db.tg_users.find_one_and_update(
            {"_id": id},
            {
                "$set": {
                    "username": username,
                    "first_name": first_name,
                    "lang": lang,
                    "role": role,
                    "last_seen_at": now,
                },
                "$setOnInsert": {"status": initial, "created_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.BEFORE,
        )
        after = await self.db.tg_users.find_one({"_id": id})
        assert after is not None
        return TgUser.from_doc(after), before is None

    async def get(self, id: int) -> TgUser | None:
        d = await self.db.tg_users.find_one({"_id": id})
        return TgUser.from_doc(d) if d else None

    async def set_status(self, id: int, status: str, *, by: int | None = None) -> None:
        await self.db.tg_users.update_one(
            {"_id": id},
            {"$set": {"status": status, "status_by": by, "status_at": utcnow()}},
        )
        log.info("tg user %s → %s (by %s)", id, status, by)

    async def list(self, status: str | None = None) -> list[TgUser]:
        q: Json = {"status": status} if status else {}
        return [
            TgUser.from_doc(d) async for d in self.db.tg_users.find(q, sort=[("created_at", 1)])
        ]

    async def admin_ids_all(self) -> list[int]:
        """Env admins plus anyone with role admin in Mongo (same thing today)."""
        ids = set(self.admin_ids)
        async for d in self.db.tg_users.find({"role": ADMIN}, {"_id": 1}):
            ids.add(int(d["_id"]))
        return sorted(ids)

    async def counts(self) -> dict[str, int]:
        out = {ACTIVE: 0, PENDING: 0, BLOCKED: 0}
        async for row in await self.db.tg_users.aggregate(
            [{"$group": {"_id": "$status", "n": {"$sum": 1}}}]
        ):
            out[str(row["_id"])] = int(row["n"])
        return out
