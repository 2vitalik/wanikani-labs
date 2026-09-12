"""Shared test doubles: a fake aiogram Bot and an AppContext factory over the test DB."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from aiogram import Bot

from wklabs.bot.context import AppContext
from wklabs.bot.notifier import Notifier
from wklabs.bot.topics import TopicManager
from wklabs.lib.accounts import AccountRepo, WkIdentity
from wklabs.lib.crypto import TokenCipher, generate_key
from wklabs.lib.db import Db
from wklabs.lib.delivery import ChatRepo, RouteRepo
from wklabs.lib.settings import Settings
from wklabs.lib.sync import SyncEngine
from wklabs.lib.users import TgUserRepo

WK1 = "07fff792-eea6-4699-9053-46f67ef92656"
WK2 = "27f9b9f5-c9ba-4412-93f4-12a776853982"


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, int | None, str]] = []
        self.topics: list[tuple[int, str]] = []
        self.renamed: list[tuple[int, int, str]] = []
        self._thread = 6

    async def send_message(self, chat_id: int, text: str, **kw: Any) -> SimpleNamespace:
        self.sent.append((chat_id, kw.get("message_thread_id"), text))
        return SimpleNamespace(message_id=len(self.sent))

    async def create_forum_topic(self, chat_id: int, name: str, **kw: Any) -> SimpleNamespace:
        self._thread += 1
        self.topics.append((chat_id, name))
        return SimpleNamespace(message_thread_id=self._thread)

    async def edit_forum_topic(self, chat_id: int, message_thread_id: int, name: str) -> None:
        self.renamed.append((chat_id, message_thread_id, name))


def make_ctx(
    db: Db, *, bot: FakeBot | None = None, admin_ids: list[int] | None = None
) -> AppContext:
    settings = Settings(tg_admin_ids=admin_ids or [], wklabs_secret_key=generate_key())
    accounts = AccountRepo(db, TokenCipher(settings.secret_key))
    users = TgUserRepo(db, admin_ids=settings.tg_admin_ids, policy=settings.access_policy)
    chats, routes = ChatRepo(db), RouteRepo(db)
    b = cast(Bot, bot) if bot is not None else None
    topics = TopicManager(b, chats, routes, accounts)
    notifier = Notifier(
        db, b, routes=routes, accounts=accounts, users=users, topics=topics, tz="Europe/Kyiv"
    )
    return AppContext(
        settings=settings,
        db=db,
        engine=SyncEngine(db, accounts),
        accounts=accounts,
        users=users,
        chats=chats,
        routes=routes,
        topics=topics,
        notifier=notifier,
        bot=b,
    )


def ident(wk_id: str = WK1, username: str = "Vitalik", level: int = 39) -> WkIdentity:
    return WkIdentity(wk_id, username, level, "lifetime", 60)
