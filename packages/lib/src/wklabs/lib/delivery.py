"""Where messages go: routes `(account | None, category) → (chat_id, thread_id)`.

Categories are delivery channels, not event kinds (`bot.routing` maps kinds
to categories). Account-scoped ones follow the account; global ones are
opted in per chat. Routes are never deleted, only disabled — a removed
account keeps its targets for a later revive. Presets fill targets in bulk
(one topic per category / per account / one for all / General); any route
can still be pointed at any topic by hand, and any number of routes may share
one topic (T26). Chats themselves live in `chats.py`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from .db import Db
from .timeutil import utcnow

log = logging.getLogger(__name__)
Json = dict[str, Any]

ACCOUNT_CATEGORIES: tuple[str, ...] = ("reviews", "milestones")
GLOBAL_CATEGORIES: tuple[str, ...] = ("subjects", "system")
CATEGORIES: tuple[str, ...] = ACCOUNT_CATEGORIES + GLOBAL_CATEGORIES
CATEGORY_ICON = {"reviews": "📝", "milestones": "🏆", "subjects": "📚", "system": "🛠"}
# Telegram forum icon colours (the only values the API accepts)
BLUE, YELLOW, PURPLE, RED = 7322096, 16766590, 13338331, 16478047
CATEGORY_COLOR = {"reviews": BLUE, "milestones": YELLOW, "subjects": PURPLE, "system": RED}

PRESET_PER_CATEGORY, PRESET_PER_ACCOUNT = "per_category", "per_account"
PRESET_ONE_TOPIC, PRESET_GENERAL = "one_topic", "general"
PRESETS: tuple[str, ...] = (
    PRESET_PER_CATEGORY,
    PRESET_PER_ACCOUNT,
    PRESET_ONE_TOPIC,
    PRESET_GENERAL,
)
PRESET_LABEL = {
    PRESET_PER_CATEGORY: "topic per category",
    PRESET_PER_ACCOUNT: "topic per account",
    PRESET_ONE_TOPIC: "one topic for all",
    PRESET_GENERAL: "General (no topics)",
}
ONE_TOPIC_NAME = "WaniKani"

STATUS_OK, STATUS_ERROR = "ok", "error"
ERR_TOPIC_DELETED, ERR_TOPIC_CLOSED = "topic deleted", "topic closed"
ERR_NO_RIGHTS, ERR_FORBIDDEN = "no rights", "forbidden"


def topic_title(category: str, label: str | None) -> str:
    icon = CATEGORY_ICON.get(category, "•")
    return f"{icon} {label} · {category}" if label else f"{icon} {category}"


def preset_topic_name(preset: str, category: str, label: str | None) -> str | None:
    """Topic a preset puts this (account label, category) into; None = General."""
    if preset == PRESET_PER_CATEGORY:
        return topic_title(category, label)
    if preset == PRESET_PER_ACCOUNT:
        return label or topic_title(category, None)
    if preset == PRESET_ONE_TOPIC:
        return ONE_TOPIC_NAME
    return None


@dataclass(slots=True)
class Route:
    id: ObjectId
    account: str | None
    category: str
    chat_id: int
    thread_id: int | None
    thread_title: str | None
    enabled: bool
    created_by: int | None
    created_at: datetime
    status: str = STATUS_OK
    error: str | None = None
    error_at: datetime | None = None
    subscribers: list[int] = field(default_factory=list)
    settings: Json = field(default_factory=dict)
    updated_by: int | None = None

    @classmethod
    def from_doc(cls, d: Json) -> Route:
        return cls(
            id=d["_id"],
            account=d.get("account"),
            category=str(d["category"]),
            chat_id=int(d["chat_id"]),
            thread_id=d.get("thread_id"),
            thread_title=d.get("thread_title"),
            enabled=bool(d.get("enabled", True)),
            created_by=d.get("created_by"),
            created_at=d.get("created_at") or utcnow(),
            status=str(d.get("status") or STATUS_OK),
            error=d.get("error"),
            error_at=d.get("error_at"),
            subscribers=[int(x) for x in d.get("subscribers") or []],
            settings=dict(d.get("settings") or {}),
            updated_by=d.get("updated_by"),
        )

    @property
    def icon(self) -> str:
        return CATEGORY_ICON.get(self.category, "•")

    @property
    def has_error(self) -> bool:
        return self.status == STATUS_ERROR


class RouteRepo:
    def __init__(self, db: Db) -> None:
        self.db = db

    async def for_target(self, account: str | None, category: str) -> list[Route]:
        q: Json = {"account": account, "category": category, "enabled": True}
        return [Route.from_doc(d) async for d in self.db.tg_routes.find(q)]

    async def for_account(
        self, account: str | None, *, include_disabled: bool = False
    ) -> list[Route]:
        q: Json = {"account": account}
        if not include_disabled:
            q["enabled"] = True
        return [Route.from_doc(d) async for d in self.db.tg_routes.find(q, sort=[("category", 1)])]

    async def for_chat(self, chat_id: int, *, include_disabled: bool = False) -> list[Route]:
        q: Json = {"chat_id": chat_id}
        if not include_disabled:
            q["enabled"] = True
        return [
            Route.from_doc(d)
            async for d in self.db.tg_routes.find(q, sort=[("account", 1), ("category", 1)])
        ]

    async def get(self, route_id: ObjectId) -> Route | None:
        d = await self.db.tg_routes.find_one({"_id": route_id})
        return Route.from_doc(d) if d else None

    async def upsert(
        self,
        account: str | None,
        category: str,
        chat_id: int,
        *,
        created_by: int | None,
        enabled: bool = True,
    ) -> Route:
        now = utcnow()
        d = await self.db.tg_routes.find_one_and_update(
            {"account": account, "category": category, "chat_id": chat_id},
            {
                "$set": {"enabled": enabled, "updated_at": now, "updated_by": created_by},
                "$setOnInsert": {
                    "thread_id": None,
                    "thread_title": None,
                    "created_by": created_by,
                    "created_at": now,
                    "status": STATUS_OK,
                    "subscribers": [],
                    "settings": {},
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        assert d is not None
        return Route.from_doc(d)

    async def set_enabled(self, route_id: ObjectId, enabled: bool) -> None:
        await self.db.tg_routes.update_one(
            {"_id": route_id}, {"$set": {"enabled": enabled, "updated_at": utcnow()}}
        )

    async def set_thread(
        self,
        route_id: ObjectId,
        thread_id: int | None,
        title: str | None,
        *,
        by: int | None = None,
    ) -> None:
        """Point a route at a topic (None = General); a new target starts healthy."""
        await self.db.tg_routes.update_one(
            {"_id": route_id},
            {
                "$set": {
                    "thread_id": thread_id,
                    "thread_title": title,
                    "status": STATUS_OK,
                    "updated_at": utcnow(),
                    "updated_by": by,
                },
                "$unset": {"error": "", "error_at": ""},
            },
        )

    async def rename_thread(self, chat_id: int, thread_id: int, title: str) -> int:
        r = await self.db.tg_routes.update_many(
            {"chat_id": chat_id, "thread_id": thread_id}, {"$set": {"thread_title": title}}
        )
        return r.modified_count

    async def clear_thread(self, chat_id: int, thread_id: int) -> int:
        """Topic gone: every route into it falls back to General (title kept for Recreate)."""
        r = await self.db.tg_routes.update_many(
            {"chat_id": chat_id, "thread_id": thread_id},
            {"$set": {"thread_id": None, "updated_at": utcnow()}},
        )
        return r.modified_count

    async def set_error(self, route_id: ObjectId, error: str) -> bool:
        """Mark a route unhealthy; True when this is news (→ tell the owner once)."""
        before = await self.db.tg_routes.find_one_and_update(
            {"_id": route_id, "error": {"$ne": error}},
            {"$set": {"status": STATUS_ERROR, "error": error, "error_at": utcnow()}},
            return_document=ReturnDocument.BEFORE,
        )
        return before is not None

    async def clear_error(self, route_id: ObjectId) -> None:
        await self.db.tg_routes.update_one(
            {"_id": route_id},
            {"$set": {"status": STATUS_OK}, "$unset": {"error": "", "error_at": ""}},
        )

    async def suspend_account(self, account: str) -> int:
        """Account removed: switch its live routes off, remembering which ones were on."""
        r = await self.db.tg_routes.update_many(
            {"account": account, "enabled": True},
            {"$set": {"enabled": False, "suspended": True, "updated_at": utcnow()}},
        )
        return r.modified_count

    async def resume_account(self, account: str) -> int:
        """Account revived: only the routes that were on at removal come back."""
        r = await self.db.tg_routes.update_many(
            {"account": account, "suspended": True},
            {"$set": {"enabled": True, "updated_at": utcnow()}, "$unset": {"suspended": ""}},
        )
        return r.modified_count

    async def disable_chat(self, chat_id: int) -> int:
        r = await self.db.tg_routes.update_many(
            {"chat_id": chat_id, "enabled": True},
            {"$set": {"enabled": False, "updated_at": utcnow()}},
        )
        return r.modified_count

    async def disable_for_owner(self, chat_id: int, accounts: list[str]) -> int:
        """`Stop here`: only this user's account routes into the chat go off."""
        if not accounts:
            return 0
        r = await self.db.tg_routes.update_many(
            {"chat_id": chat_id, "account": {"$in": accounts}, "enabled": True},
            {"$set": {"enabled": False, "updated_at": utcnow()}},
        )
        return r.modified_count

    async def ensure_account_routes(
        self, account: str, chat_id: int, *, created_by: int | None
    ) -> list[Route]:
        return [
            await self.upsert(account, cat, chat_id, created_by=created_by)
            for cat in ACCOUNT_CATEGORIES
        ]

    async def move_account(
        self, account: str, chat_id: int, *, created_by: int | None
    ) -> list[Route]:
        """All account categories → this chat; routes elsewhere are disabled (kept)."""
        await self.db.tg_routes.update_many(
            {"account": account, "chat_id": {"$ne": chat_id}},
            {"$set": {"enabled": False, "updated_at": utcnow()}},
        )
        return await self.ensure_account_routes(account, chat_id, created_by=created_by)

    async def chats_for_account(self, account: str) -> list[int]:
        return sorted({int(r.chat_id) for r in await self.for_account(account)})

    async def migrate_chat(self, old: int, new: int) -> int:
        r = await self.db.tg_routes.update_many(
            {"chat_id": old}, {"$set": {"chat_id": new, "updated_at": utcnow()}}
        )
        return r.modified_count
