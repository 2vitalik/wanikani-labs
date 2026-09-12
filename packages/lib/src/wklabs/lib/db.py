"""Mongo access (PyMongo native async). One `Db` per process, passed explicitly.

Collections (T01, T14/T21): current-state per WaniKani resource + `history`
(append-only versions) + `events` (derived) + sync bookkeeping + `accounts`
(WaniKani accounts, encrypted tokens) + `tg_*` (Telegram delivery layer).
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

from .settings import Settings, get_settings

Doc = dict[str, Any]

# resource name -> collection name (current state)
CURRENT: dict[str, str] = {
    "subjects": "subjects",
    "assignments": "assignments",
    "review_statistics": "review_statistics",
    "level_progressions": "level_progressions",
    "study_materials": "study_materials",
    "resets": "resets",
    "srs_systems": "srs_systems",
    "voice_actors": "voice_actors",
    "user": "users",
    "summary": "summaries",
}

HISTORY = "history"
EVENTS = "events"
SYNC_STATE = "sync_state"
SYNC_RUNS = "sync_runs"
ACCOUNTS = "accounts"
TG_USERS = "tg_users"
TG_CHATS = "tg_chats"
TG_ROUTES = "tg_routes"
TG_MESSAGES = "tg_messages"
TG_FSM = "tg_fsm"  # aiogram PyMongoStorage (dialog state)

_INDEXES: dict[str, list[tuple[list[tuple[str, int]], dict[str, Any]]]] = {
    "subjects": [
        ([("type", ASCENDING), ("level", ASCENDING)], {}),
        ([("updated_at", DESCENDING)], {}),
    ],
    "assignments": [
        ([("account", ASCENDING), ("subject_id", ASCENDING)], {"unique": True}),
        ([("account", ASCENDING), ("srs_stage", ASCENDING)], {}),
        ([("account", ASCENDING), ("available_at", ASCENDING)], {}),
        ([("updated_at", DESCENDING)], {}),
    ],
    "review_statistics": [
        ([("account", ASCENDING), ("subject_id", ASCENDING)], {"unique": True}),
        ([("updated_at", DESCENDING)], {}),
    ],
    "level_progressions": [([("account", ASCENDING), ("level", ASCENDING)], {})],
    "study_materials": [([("account", ASCENDING), ("subject_id", ASCENDING)], {})],
    "resets": [([("account", ASCENDING)], {})],
    HISTORY: [
        (
            [
                ("resource", ASCENDING),
                ("account", ASCENDING),
                ("resource_id", ASCENDING),
                ("data_updated_at", ASCENDING),
            ],
            {"unique": True},
        ),
        ([("updated_at", DESCENDING)], {}),
        ([("account", ASCENDING), ("updated_at", DESCENDING)], {}),
    ],
    EVENTS: [
        ([("history_id", ASCENDING), ("kind", ASCENDING)], {"unique": True}),
        ([("notified_at", ASCENDING), ("at", ASCENDING)], {}),
        ([("account", ASCENDING), ("at", DESCENDING)], {}),
        ([("account", ASCENDING), ("kind", ASCENDING), ("at", DESCENDING)], {}),
        ([("subject_id", ASCENDING), ("at", DESCENDING)], {}),
    ],
    SYNC_RUNS: [([("started_at", DESCENDING)], {})],
    ACCOUNTS: [
        ([("wk_id", ASCENDING)], {"unique": True}),
        ([("owner_tg_id", ASCENDING), ("status", ASCENDING)], {}),
    ],
    TG_USERS: [([("status", ASCENDING)], {})],
    TG_ROUTES: [
        (
            [("account", ASCENDING), ("category", ASCENDING), ("chat_id", ASCENDING)],
            {"unique": True},
        ),
        ([("chat_id", ASCENDING), ("thread_id", ASCENDING)], {}),
        ([("account", ASCENDING), ("enabled", ASCENDING)], {}),
    ],
    TG_MESSAGES: [([("sent_at", DESCENDING)], {})],
}


class Db:
    def __init__(self, client: AsyncMongoClient[Doc], name: str) -> None:
        self.client = client
        self.name = name
        self.database: AsyncDatabase[Doc] = client[name]

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> Db:
        s = settings or get_settings()
        return cls.connect(s.mongo_uri, s.mongo_db)

    @classmethod
    def connect(cls, uri: str, name: str) -> Db:
        client: AsyncMongoClient[Doc] = AsyncMongoClient(uri, tz_aware=True, tzinfo=UTC)
        return cls(client, name)

    # -- collections -------------------------------------------------------
    def col(self, name: str) -> AsyncCollection[Doc]:
        return self.database[name]

    def current(self, resource: str) -> AsyncCollection[Doc]:
        return self.database[CURRENT[resource]]

    @property
    def history(self) -> AsyncCollection[Doc]:
        return self.database[HISTORY]

    @property
    def events(self) -> AsyncCollection[Doc]:
        return self.database[EVENTS]

    @property
    def sync_state(self) -> AsyncCollection[Doc]:
        return self.database[SYNC_STATE]

    @property
    def sync_runs(self) -> AsyncCollection[Doc]:
        return self.database[SYNC_RUNS]

    @property
    def accounts(self) -> AsyncCollection[Doc]:
        return self.database[ACCOUNTS]

    @property
    def tg_users(self) -> AsyncCollection[Doc]:
        return self.database[TG_USERS]

    @property
    def tg_chats(self) -> AsyncCollection[Doc]:
        return self.database[TG_CHATS]

    @property
    def tg_routes(self) -> AsyncCollection[Doc]:
        return self.database[TG_ROUTES]

    @property
    def tg_messages(self) -> AsyncCollection[Doc]:
        return self.database[TG_MESSAGES]

    # -- lifecycle ---------------------------------------------------------
    async def ping(self) -> None:
        await self.database.command("ping")

    async def ensure_indexes(self) -> None:
        for coll, specs in _INDEXES.items():
            for keys, kwargs in specs:
                await self.database[coll].create_index(keys, **kwargs)

    async def drop_all(self) -> None:
        """Tests only."""
        await self.client.drop_database(self.name)

    async def close(self) -> None:
        await self.client.close()
