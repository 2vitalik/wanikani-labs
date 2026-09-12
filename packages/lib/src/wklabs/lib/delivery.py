"""Where messages go: Telegram chats the bot delivers to, and routes
`(account | None, category) → (chat_id, thread_id)`.

Categories are delivery channels, not event kinds (`bot.routing` maps kinds
to categories). Account-scoped ones follow the account; global ones are
opted in per chat. Routes are never deleted, only disabled — a removed
account keeps its forum topics for a later revive.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
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

LAYOUT_TOPICS, LAYOUT_SINGLE = "topics", "single"


def topic_title(category: str, label: str | None) -> str:
    icon = CATEGORY_ICON.get(category, "•")
    return f"{icon} {label} · {category}" if label else f"{icon} {category}"


@dataclass(slots=True)
class Chat:
    id: int
    type: str  # private | group | supergroup
    title: str | None
    is_forum: bool
    layout: str
    set_up_by: int | None
    bot_is_admin: bool
    can_manage_topics: bool

    @classmethod
    def from_doc(cls, d: Json) -> Chat:
        return cls(
            id=int(d["_id"]),
            type=str(d.get("type") or "private"),
            title=d.get("title"),
            is_forum=bool(d.get("is_forum")),
            layout=str(d.get("layout") or LAYOUT_SINGLE),
            set_up_by=d.get("set_up_by"),
            bot_is_admin=bool(d.get("bot_is_admin")),
            can_manage_topics=bool(d.get("can_manage_topics")),
        )

    @property
    def is_private(self) -> bool:
        return self.type == "private"

    @property
    def name(self) -> str:
        return "private" if self.is_private else (self.title or str(self.id))

    @property
    def topics_possible(self) -> bool:
        return self.is_forum and self.can_manage_topics


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
        )


class ChatRepo:
    def __init__(self, db: Db) -> None:
        self.db = db

    async def get(self, chat_id: int) -> Chat | None:
        d = await self.db.tg_chats.find_one({"_id": chat_id})
        return Chat.from_doc(d) if d else None

    async def upsert(
        self,
        chat_id: int,
        *,
        type: str,
        title: str | None = None,
        is_forum: bool = False,
        layout: str | None = None,
        set_up_by: int | None = None,
        bot_is_admin: bool | None = None,
        can_manage_topics: bool | None = None,
    ) -> Chat:
        now = utcnow()
        fields: Json = {"type": type, "title": title, "is_forum": is_forum, "checked_at": now}
        for k, v in (
            ("layout", layout),
            ("set_up_by", set_up_by),
            ("bot_is_admin", bot_is_admin),
            ("can_manage_topics", can_manage_topics),
        ):
            if v is not None:
                fields[k] = v
        d = await self.db.tg_chats.find_one_and_update(
            {"_id": chat_id},
            {"$set": fields, "$setOnInsert": {"created_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        assert d is not None
        return Chat.from_doc(d)

    async def ensure_private(self, tg_id: int) -> Chat:
        return await self.upsert(tg_id, type="private", layout=LAYOUT_SINGLE, set_up_by=tg_id)

    async def for_user(self, tg_id: int) -> list[Chat]:
        """Chats this user can deliver to: their private chat + chats they set up."""
        q: Json = {"$or": [{"_id": tg_id}, {"set_up_by": tg_id}]}
        chats = [Chat.from_doc(d) async for d in self.db.tg_chats.find(q, sort=[("created_at", 1)])]
        if not any(c.id == tg_id for c in chats):
            chats.insert(0, await self.ensure_private(tg_id))
        return chats


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
        return [Route.from_doc(d) async for d in self.db.tg_routes.find(q)]

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
                "$set": {"enabled": enabled, "updated_at": now},
                "$setOnInsert": {
                    "thread_id": None,
                    "thread_title": None,
                    "created_by": created_by,
                    "created_at": now,
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
        self, route_id: ObjectId, thread_id: int | None, title: str | None
    ) -> None:
        await self.db.tg_routes.update_one(
            {"_id": route_id},
            {"$set": {"thread_id": thread_id, "thread_title": title, "updated_at": utcnow()}},
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
