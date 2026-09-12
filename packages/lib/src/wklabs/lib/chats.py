"""Telegram chats the bot can post to: registry, rights snapshot, known forum topics.

A chat gets here three ways, all idempotent upserts: the user picks it in
private (`request_chat`), the bot is added by hand (`my_chat_member`), or any
update is seen in the chat. `apply_inspection` (get_chat + get_chat_member)
refreshes the rights snapshot. The Bot API cannot list forum topics, so
`topics` holds only the ones the bot created or saw messages in.
"""

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

PRIVATE, GROUP, SUPERGROUP, CHANNEL = "private", "group", "supergroup", "channel"
# bot membership (Telegram ChatMember.status) + "seen only, never inspected"
MEMBER, ADMIN, RESTRICTED = "member", "administrator", "restricted"
LEFT, KICKED, UNKNOWN = "left", "kicked", "unknown"
GONE = (LEFT, KICKED)

VIA_ADDED, VIA_PICKED, VIA_MESSAGE, VIA_SETUP, VIA_VERIFIED = (
    "added",
    "picked",
    "message",
    "setup",
    "verified",
)

# hint codes (texts live in the bot): what is wrong + the one action that fixes it
HINT_BASIC_GROUP = "basic_group"
HINT_NOT_FORUM = "not_forum"
HINT_FORUM_NOT_ADMIN = "forum_not_admin"
HINT_NO_TOPICS_RIGHT = "no_topics_right"
HINT_CANNOT_POST = "cannot_post"
HINT_CHANNEL_NO_POST = "channel_no_post"
HINT_GONE = "gone"
HINT_UNKNOWN = "unknown"

# legacy `layout` (T18) → preset (T26)
_LEGACY_PRESET = {"topics": "per_category", "single": "general"}


@dataclass(slots=True)
class Rights:
    can_post: bool = True
    can_manage_topics: bool = False
    can_delete: bool = False
    can_pin: bool = False

    def to_doc(self) -> Json:
        return {
            "can_post": self.can_post,
            "can_manage_topics": self.can_manage_topics,
            "can_delete": self.can_delete,
            "can_pin": self.can_pin,
        }

    @classmethod
    def from_doc(cls, d: Json | None) -> Rights:
        d = d or {}
        return cls(
            can_post=bool(d.get("can_post", True)),
            can_manage_topics=bool(d.get("can_manage_topics")),
            can_delete=bool(d.get("can_delete")),
            can_pin=bool(d.get("can_pin")),
        )


@dataclass(slots=True)
class Topic:
    thread_id: int
    name: str
    by_bot: bool = False
    bot_name: str | None = None  # the name the bot gave it (rename rule, T26 §3)
    closed: bool = False
    seen_at: datetime | None = None

    @classmethod
    def from_doc(cls, thread_id: int, d: Json) -> Topic:
        return cls(
            thread_id=thread_id,
            name=str(d.get("name") or f"topic {thread_id}"),
            by_bot=bool(d.get("by_bot")),
            bot_name=d.get("bot_name"),
            closed=bool(d.get("closed")),
            seen_at=d.get("seen_at"),
        )


@dataclass(slots=True)
class Inspection:
    """What one `get_chat` + `get_chat_member(me)` told us (pure data, no aiogram)."""

    type: str
    title: str | None
    is_forum: bool
    status: str
    rights: Rights
    member_can_topics: bool = False


@dataclass(slots=True)
class Chat:
    id: int
    type: str
    title: str | None
    is_forum: bool
    status: str
    rights: Rights
    member_can_topics: bool
    member_ids: list[int]
    topics: dict[int, Topic]
    preset: str | None
    added_by: int | None
    checked_at: datetime | None
    last_seen_at: datetime | None
    migrated_to: int | None
    greeted_at: datetime | None
    forgotten_at: datetime | None

    @classmethod
    def from_doc(cls, d: Json) -> Chat:
        type_ = str(d.get("type") or PRIVATE)
        rights = Rights.from_doc(d.get("rights"))
        status = d.get("status")
        if "rights" not in d and (d.get("bot_is_admin") or d.get("can_manage_topics")):
            rights = Rights(can_manage_topics=bool(d.get("can_manage_topics")))
            status = status or ADMIN
        if status is None:
            status = MEMBER if type_ == PRIVATE else UNKNOWN
        member_ids = [int(x) for x in d.get("member_ids") or []]
        legacy_owner = d.get("set_up_by")
        if legacy_owner is not None and legacy_owner not in member_ids:
            member_ids.append(int(legacy_owner))
        topics = {
            int(tid): Topic.from_doc(int(tid), td) for tid, td in (d.get("topics") or {}).items()
        }
        return cls(
            id=int(d["_id"]),
            type=type_,
            title=d.get("title"),
            is_forum=bool(d.get("is_forum")),
            status=str(status),
            rights=rights,
            member_can_topics=bool(d.get("member_can_topics")),
            member_ids=member_ids,
            topics=topics,
            preset=d.get("preset") or _LEGACY_PRESET.get(str(d.get("layout") or "")),
            added_by=d.get("added_by"),
            checked_at=d.get("checked_at"),
            last_seen_at=d.get("last_seen_at"),
            migrated_to=d.get("migrated_to"),
            greeted_at=d.get("greeted_at"),
            forgotten_at=d.get("forgotten_at"),
        )

    @property
    def is_private(self) -> bool:
        return self.type == PRIVATE

    @property
    def is_channel(self) -> bool:
        return self.type == CHANNEL

    @property
    def is_group(self) -> bool:
        return self.type in (GROUP, SUPERGROUP)

    @property
    def name(self) -> str:
        return "private" if self.is_private else (self.title or str(self.id))

    @property
    def kind(self) -> str:
        return "forum" if self.is_forum else self.type

    @property
    def present(self) -> bool:
        return self.status not in GONE

    @property
    def is_admin(self) -> bool:
        return self.status == ADMIN

    @property
    def inspected(self) -> bool:
        return self.status != UNKNOWN

    @property
    def can_post(self) -> bool:
        if self.is_private:
            return True
        return self.present and self.rights.can_post

    @property
    def topics_possible(self) -> bool:
        """The bot may create/rename topics here (forum + admin + Manage Topics)."""
        return self.is_forum and self.present and self.is_admin and self.rights.can_manage_topics

    def topic(self, thread_id: int | None) -> Topic | None:
        return self.topics.get(thread_id) if thread_id is not None else None

    def topic_by_name(self, name: str) -> Topic | None:
        for t in self.topics.values():
            if t.name == name:
                return t
        return None

    def is_member(self, tg_id: int) -> bool:
        return (self.is_private and self.id == tg_id) or tg_id in self.member_ids


def hints(chat: Chat) -> list[str]:
    """What is wrong with this chat as a target, most severe first (codes; texts in the bot)."""
    if chat.is_private:
        return []
    if not chat.present:
        return [HINT_GONE]
    if not chat.inspected:
        return [HINT_UNKNOWN]
    out: list[str] = []
    if not chat.rights.can_post:
        out.append(HINT_CHANNEL_NO_POST if chat.is_channel else HINT_CANNOT_POST)
    if chat.is_channel:
        return out
    if chat.type == GROUP:
        out.append(HINT_BASIC_GROUP)
    elif not chat.is_forum:
        out.append(HINT_NOT_FORUM)
    elif not chat.is_admin:
        out.append(HINT_FORUM_NOT_ADMIN)
    elif not chat.rights.can_manage_topics:
        out.append(HINT_NO_TOPICS_RIGHT)
    return out


class ChatRepo:
    def __init__(self, db: Db) -> None:
        self.db = db

    async def get(self, chat_id: int) -> Chat | None:
        d = await self.db.tg_chats.find_one({"_id": chat_id})
        return Chat.from_doc(d) if d else None

    async def seen(
        self,
        chat_id: int,
        *,
        type: str,
        title: str | None = None,
        is_forum: bool | None = None,
        member: int | None = None,
        via: str = VIA_MESSAGE,
        thread: tuple[int, str | None] | None = None,
    ) -> Chat:
        """Cheap upsert from any update seen in the chat (middleware, commands)."""
        now = utcnow()
        set_: Json = {"type": type, "last_seen_at": now}
        if title is not None:
            set_["title"] = title
        if is_forum is not None:
            set_["is_forum"] = is_forum
        if thread is not None:
            tid, name = thread
            set_[f"topics.{tid}.seen_at"] = now
            if name:
                set_[f"topics.{tid}.name"] = name
        update: Json = {
            "$set": set_,
            "$setOnInsert": {"status": MEMBER if type == PRIVATE else UNKNOWN, "created_at": now},
            "$unset": {"forgotten_at": ""},
        }
        if member is not None:
            update["$addToSet"] = {"member_ids": member}
            set_[f"members.{member}.seen_at"] = now
            set_[f"members.{member}.via"] = via
        d = await self.db.tg_chats.find_one_and_update(
            {"_id": chat_id}, update, upsert=True, return_document=ReturnDocument.AFTER
        )
        assert d is not None
        return Chat.from_doc(d)

    async def apply_inspection(
        self, chat_id: int, insp: Inspection, *, added_by: int | None = None
    ) -> Chat:
        now = utcnow()
        set_: Json = {
            "type": insp.type,
            "title": insp.title,
            "is_forum": insp.is_forum,
            "status": insp.status,
            "rights": insp.rights.to_doc(),
            "member_can_topics": insp.member_can_topics,
            "checked_at": now,
            "last_seen_at": now,
        }
        if added_by is not None:
            set_["added_by"] = added_by
        d = await self.db.tg_chats.find_one_and_update(
            {"_id": chat_id},
            {"$set": set_, "$setOnInsert": {"created_at": now}, "$unset": {"forgotten_at": ""}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        assert d is not None
        return Chat.from_doc(d)

    async def set_status(self, chat_id: int, status: str) -> None:
        await self.db.tg_chats.update_one(
            {"_id": chat_id}, {"$set": {"status": status, "checked_at": utcnow()}}
        )

    async def add_member(self, chat_id: int, tg_id: int, via: str) -> None:
        await self.db.tg_chats.update_one(
            {"_id": chat_id},
            {
                "$addToSet": {"member_ids": tg_id},
                "$set": {f"members.{tg_id}.seen_at": utcnow(), f"members.{tg_id}.via": via},
            },
        )

    # ------------------------------------------------------------ topics
    async def remember_topic(
        self, chat_id: int, thread_id: int, name: str, *, by_bot: bool = False
    ) -> None:
        set_: Json = {f"topics.{thread_id}.name": name, f"topics.{thread_id}.seen_at": utcnow()}
        if by_bot:
            set_[f"topics.{thread_id}.by_bot"] = True
            set_[f"topics.{thread_id}.bot_name"] = name
        await self.db.tg_chats.update_one({"_id": chat_id}, {"$set": set_})

    async def topic_closed(self, chat_id: int, thread_id: int, closed: bool = True) -> None:
        await self.db.tg_chats.update_one(
            {"_id": chat_id}, {"$set": {f"topics.{thread_id}.closed": closed}}
        )

    async def topic_gone(self, chat_id: int, thread_id: int) -> None:
        await self.db.tg_chats.update_one({"_id": chat_id}, {"$unset": {f"topics.{thread_id}": ""}})

    # ------------------------------------------------------------- misc
    async def set_preset(self, chat_id: int, preset: str) -> None:
        await self.db.tg_chats.update_one({"_id": chat_id}, {"$set": {"preset": preset}})

    async def set_greeted(self, chat_id: int) -> None:
        await self.db.tg_chats.update_one({"_id": chat_id}, {"$set": {"greeted_at": utcnow()}})

    async def forget(self, chat_id: int) -> None:
        """Hide a gone chat from lists; any later update in it brings it back."""
        await self.db.tg_chats.update_one({"_id": chat_id}, {"$set": {"forgotten_at": utcnow()}})

    async def migrate(self, old: int, new: int) -> Chat | None:
        """group → supergroup: the chat keeps everything under its new id (routes: RouteRepo)."""
        d = await self.db.tg_chats.find_one({"_id": old})
        if d is None:
            return None
        if d.get("migrated_to") == new:
            return await self.get(new)
        existing = await self.db.tg_chats.find_one({"_id": new})
        if existing is None:
            moved = {k: v for k, v in d.items() if k not in ("_id", "migrated_to")}
            moved.update({"_id": new, "type": SUPERGROUP, "migrated_from": old})
            await self.db.tg_chats.insert_one(moved)
        else:
            await self.db.tg_chats.update_one(
                {"_id": new},
                {
                    "$addToSet": {"member_ids": {"$each": d.get("member_ids") or []}},
                    "$set": {"migrated_from": old},
                },
            )
        await self.db.tg_chats.update_one(
            {"_id": old}, {"$set": {"migrated_to": new, "status": LEFT}}
        )
        log.info("chat %s migrated to %s", old, new)
        return await self.get(new)

    async def ensure_private(self, tg_id: int) -> Chat:
        return await self.seen(tg_id, type=PRIVATE, member=tg_id, via=VIA_MESSAGE)

    async def visible_to(self, tg_id: int, *, admin: bool = False) -> list[Chat]:
        """Chats this user may target: private first, then groups they are known in (admin: all)."""
        chats = [await self.ensure_private(tg_id)]
        q: Json = {
            "type": {"$ne": PRIVATE},
            "forgotten_at": {"$exists": False},
            "migrated_to": {"$exists": False},
        }
        if not admin:
            q["member_ids"] = tg_id
        async for d in self.db.tg_chats.find(q, sort=[("last_seen_at", -1)]):
            chats.append(Chat.from_doc(d))
        return chats

    async def normalize_legacy(self) -> int:
        """One-off at start: T18 fields (`set_up_by`, `layout`, `bot_is_admin`) → T26 shape."""
        n = 0
        q: Json = {"$or": [{"set_up_by": {"$exists": True}}, {"layout": {"$exists": True}}]}
        async for d in self.db.tg_chats.find(q):
            chat = Chat.from_doc(d)  # reads both shapes
            set_: Json = {
                "member_ids": chat.member_ids,
                "status": chat.status,
                "rights": chat.rights.to_doc(),
            }
            if chat.preset:
                set_["preset"] = chat.preset
            owner = d.get("set_up_by")
            if owner is not None:
                set_[f"members.{owner}.via"] = VIA_SETUP
            await self.db.tg_chats.update_one(
                {"_id": d["_id"]},
                {
                    "$set": set_,
                    "$unset": {
                        "set_up_by": "",
                        "layout": "",
                        "bot_is_admin": "",
                        "can_manage_topics": "",
                    },
                },
            )
            n += 1
        if n:
            log.info("normalized %d legacy chat document(s)", n)
        return n
