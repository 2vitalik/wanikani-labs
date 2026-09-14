"""Where messages go: routes `(account | None, kind) → (chat_id, thread_id)` + settings.

A route is one *notification*: kind (what and when) x target (chat, topic) x
its own settings (T32 §0). Any number of routes may share a kind, a chat or a
topic — "session with items → topic A" and "session counts only → topic B" are
two routes of kind `session`. Account-scoped kinds follow the account; global
ones are opted in per chat. Routes are never deleted, only disabled — a
removed account keeps its targets for a later revive. Presets fill targets in
bulk (one topic per kind / per account / one for all / General). Chats
themselves live in `chats.py`; the settings registry in `notify_settings.py`.
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

# Telegram forum icon colours (the only values the API accepts)
BLUE, YELLOW, PURPLE, GREEN, RED = 7322096, 16766590, 13338331, 9367192, 16478047


@dataclass(frozen=True, slots=True)
class Kind:
    key: str
    icon: str
    title: str
    blurb: str  # one line under the name in ➕ Add…
    scope: str  # account | global
    topic: str  # word used in preset topic names (`📝 Vitalik · reviews`)
    color: int


KINDS: dict[str, Kind] = {
    k.key: k
    for k in (
        Kind(
            "session",
            "🧘",
            "Session summary",
            "after each study session",
            "account",
            "sessions",
            GREEN,
        ),
        Kind("live", "📝", "Live reviews", "every poll, as it happens", "account", "reviews", BLUE),
        Kind(
            "milestones",
            "🏆",
            "Milestones",
            "level-ups, guru, burns",
            "account",
            "milestones",
            YELLOW,
        ),
        Kind(
            "subjects",
            "📚",
            "Subjects",
            "WaniKani content changes, shared per chat",
            "global",
            "subjects",
            PURPLE,
        ),
        Kind("system", "🛠", "System", "bot alerts for admins", "global", "system", RED),
    )
}
ACCOUNT_KINDS: tuple[str, ...] = ("session", "live", "milestones")
GLOBAL_KINDS: tuple[str, ...] = ("subjects", "system")
ADDABLE_KINDS: tuple[str, ...] = ACCOUNT_KINDS  # what ➕ Add… offers
DEFAULT_KINDS: tuple[str, ...] = ("session", "milestones")  # a new account starts with these
LEGACY_KIND = {"reviews": "live"}  # T30 categories → kinds
KIND_ICON = {k: v.icon for k, v in KINDS.items()}
KIND_COLOR = {k: v.color for k, v in KINDS.items()}

PRESET_PER_CATEGORY, PRESET_PER_ACCOUNT = "per_category", "per_account"
PRESET_ONE_TOPIC, PRESET_GENERAL = "one_topic", "general"
PRESETS: tuple[str, ...] = (
    PRESET_PER_CATEGORY,
    PRESET_PER_ACCOUNT,
    PRESET_ONE_TOPIC,
    PRESET_GENERAL,
)
PRESET_LABEL = {
    PRESET_PER_CATEGORY: "topic per kind",
    PRESET_PER_ACCOUNT: "topic per account",
    PRESET_ONE_TOPIC: "one topic for all",
    PRESET_GENERAL: "General (no topics)",
}
ONE_TOPIC_NAME = "WaniKani"

STATUS_OK, STATUS_ERROR = "ok", "error"
ERR_TOPIC_DELETED, ERR_TOPIC_CLOSED = "topic deleted", "topic closed"
ERR_NO_RIGHTS, ERR_FORBIDDEN = "no rights", "forbidden"


def kind_of(value: Any) -> str:
    return LEGACY_KIND.get(str(value), str(value))


def kind_icon(kind: str) -> str:
    return KIND_ICON.get(kind, "•")


def kind_title(kind: str) -> str:
    return KINDS[kind].title if kind in KINDS else kind


def topic_title(kind: str, label: str | None) -> str:
    word = KINDS[kind].topic if kind in KINDS else kind
    icon = kind_icon(kind)
    return f"{icon} {label} · {word}" if label else f"{icon} {word}"


def preset_topic_name(preset: str, kind: str, label: str | None) -> str | None:
    """Topic a preset puts this (account label, kind) into; None = General."""
    if preset == PRESET_PER_CATEGORY:
        return topic_title(kind, label)
    if preset == PRESET_PER_ACCOUNT:
        return label or topic_title(kind, None)
    if preset == PRESET_ONE_TOPIC:
        return ONE_TOPIC_NAME
    return None


@dataclass(slots=True)
class Route:
    id: ObjectId
    account: str | None
    kind: str
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
            kind=kind_of(d.get("kind") or d.get("category")),
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
        return kind_icon(self.kind)

    @property
    def title(self) -> str:
        return kind_title(self.kind)

    @property
    def has_error(self) -> bool:
        return self.status == STATUS_ERROR


def _new_doc(
    account: str | None,
    kind: str,
    chat_id: int,
    *,
    created_by: int | None,
    now: datetime,
    enabled: bool = True,
    settings: Json | None = None,
) -> Json:
    return {
        "_id": ObjectId(),
        "account": account,
        "kind": kind,
        "chat_id": chat_id,
        "thread_id": None,
        "thread_title": None,
        "enabled": enabled,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
        "updated_by": created_by,
        "status": STATUS_OK,
        "subscribers": [],
        "settings": dict(settings or {}),
    }


class RouteRepo:
    def __init__(self, db: Db) -> None:
        self.db = db

    async def for_target(self, account: str | None, kind: str) -> list[Route]:
        q: Json = {"account": account, "kind": kind, "enabled": True}
        return [
            Route.from_doc(d) async for d in self.db.tg_routes.find(q, sort=[("created_at", 1)])
        ]

    async def for_kind(self, kind: str) -> list[Route]:
        """Every enabled route of a kind (all accounts) — the session pass starts here."""
        q: Json = {"kind": kind, "enabled": True}
        return [Route.from_doc(d) async for d in self.db.tg_routes.find(q, sort=[("account", 1)])]

    async def for_account(
        self, account: str | None, *, include_disabled: bool = False
    ) -> list[Route]:
        q: Json = {"account": account}
        if not include_disabled:
            q["enabled"] = True
        return [
            Route.from_doc(d)
            async for d in self.db.tg_routes.find(q, sort=[("kind", 1), ("created_at", 1)])
        ]

    async def for_chat(self, chat_id: int, *, include_disabled: bool = False) -> list[Route]:
        q: Json = {"chat_id": chat_id}
        if not include_disabled:
            q["enabled"] = True
        return [
            Route.from_doc(d)
            async for d in self.db.tg_routes.find(
                q, sort=[("account", 1), ("kind", 1), ("created_at", 1)]
            )
        ]

    async def get(self, route_id: ObjectId) -> Route | None:
        d = await self.db.tg_routes.find_one({"_id": route_id})
        return Route.from_doc(d) if d else None

    async def upsert(
        self,
        account: str | None,
        kind: str,
        chat_id: int,
        *,
        created_by: int | None,
        enabled: bool = True,
    ) -> Route:
        """The first route of this kind in the chat (switched on), or a new one."""
        now = utcnow()
        d = await self.db.tg_routes.find_one_and_update(
            {"account": account, "kind": kind, "chat_id": chat_id},
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

    async def subscribe(self, kind: str, chat_id: int, tg_id: int) -> Route:
        """Global kind in a chat: one route, on while anyone is subscribed (T22 §2)."""
        now = utcnow()
        d = await self.db.tg_routes.find_one_and_update(
            {"account": None, "kind": kind, "chat_id": chat_id},
            {
                "$addToSet": {"subscribers": tg_id},
                "$set": {"enabled": True, "updated_at": now, "updated_by": tg_id},
                "$setOnInsert": {
                    "thread_id": None,
                    "thread_title": None,
                    "created_by": tg_id,
                    "created_at": now,
                    "status": STATUS_OK,
                    "settings": {},
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        assert d is not None
        return Route.from_doc(d)

    async def unsubscribe(self, kind: str, chat_id: int, tg_id: int) -> Route | None:
        now = utcnow()
        d = await self.db.tg_routes.find_one_and_update(
            {"account": None, "kind": kind, "chat_id": chat_id},
            {"$pull": {"subscribers": tg_id}, "$set": {"updated_at": now, "updated_by": tg_id}},
            return_document=ReturnDocument.AFTER,
        )
        if d is None:
            return None
        if not d.get("subscribers"):
            await self.db.tg_routes.update_one({"_id": d["_id"]}, {"$set": {"enabled": False}})
            d["enabled"] = False
        return Route.from_doc(d)

    async def add_target(
        self,
        account: str | None,
        kind: str,
        chat_id: int,
        thread_id: int | None,
        title: str | None,
        *,
        by: int | None,
        settings: Json | None = None,
    ) -> Route:
        """A new notification of this kind into chat/topic; existing routes untouched."""
        doc = _new_doc(account, kind, chat_id, created_by=by, now=utcnow(), settings=settings)
        doc.update({"thread_id": thread_id, "thread_title": title})
        await self.db.tg_routes.insert_one(doc)
        return Route.from_doc(doc)

    async def move_route(
        self,
        route: Route,
        chat_id: int,
        thread_id: int | None,
        title: str | None,
        *,
        by: int | None,
    ) -> Route:
        """Retarget one route: same chat → new topic; other chat → old off, copy on."""
        if route.chat_id == chat_id:
            await self.set_thread(route.id, thread_id, title, by=by)
            return await self.get(route.id) or route
        await self.set_enabled(route.id, False)
        return await self.add_target(
            route.account, route.kind, chat_id, thread_id, title, by=by, settings=route.settings
        )

    async def set_setting(self, route_id: ObjectId, key: str, value: Any, *, by: int) -> None:
        await self.db.tg_routes.update_one(
            {"_id": route_id},
            {"$set": {f"settings.{key}": value, "updated_at": utcnow(), "updated_by": by}},
        )

    async def reset_settings(self, route_id: ObjectId, *, by: int) -> None:
        await self.db.tg_routes.update_one(
            {"_id": route_id}, {"$set": {"settings": {}, "updated_at": utcnow(), "updated_by": by}}
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
        self,
        account: str,
        chat_id: int,
        *,
        created_by: int | None,
        kinds: tuple[str, ...] = DEFAULT_KINDS,
    ) -> list[Route]:
        return [await self.upsert(account, k, chat_id, created_by=created_by) for k in kinds]

    async def move_account(
        self, account: str, chat_id: int, *, created_by: int | None
    ) -> list[Route]:
        """Every enabled notification of the account → this chat (settings travel along).

        Routes elsewhere are disabled (kept); an account without any starts with the defaults."""
        live = await self.for_account(account)
        if not live:
            return await self.ensure_account_routes(account, chat_id, created_by=created_by)
        out: list[Route] = []
        for r in live:
            if r.chat_id == chat_id:
                out.append(r)
                continue
            await self.set_enabled(r.id, False)
            out.append(
                await self.add_target(
                    account, r.kind, chat_id, None, None, by=created_by, settings=r.settings
                )
            )
        return out

    async def chats_for_account(self, account: str) -> list[int]:
        return sorted({int(r.chat_id) for r in await self.for_account(account)})

    async def migrate_chat(self, old: int, new: int) -> int:
        r = await self.db.tg_routes.update_many(
            {"chat_id": old}, {"$set": {"chat_id": new, "updated_at": utcnow()}}
        )
        return r.modified_count

    async def normalize_legacy(self) -> int:
        """One-off at start: T30 `category` → `kind` (`reviews` → `live`)."""
        n = 0
        async for d in self.db.tg_routes.find({"category": {"$exists": True}}):
            await self.db.tg_routes.update_one(
                {"_id": d["_id"]},
                {"$set": {"kind": kind_of(d["category"])}, "$unset": {"category": ""}},
            )
            n += 1
        if n:
            log.info("normalized %d legacy route document(s): category → kind", n)
        return n
