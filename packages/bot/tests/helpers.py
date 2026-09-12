"""Shared test doubles: a fake aiogram Bot and an AppContext factory over the test DB."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import SendMessage
from aiogram.types import (
    AcceptedGiftTypes,
    ChatFullInfo,
    ChatMember,
    ChatMemberAdministrator,
    ChatMemberLeft,
    ChatMemberMember,
    ChatPermissions,
    User,
)

from wklabs.bot.context import AppContext
from wklabs.bot.notifier import Notifier
from wklabs.bot.topics import TopicManager
from wklabs.lib.accounts import AccountRepo, WkIdentity
from wklabs.lib.chats import ChatRepo
from wklabs.lib.crypto import TokenCipher, generate_key
from wklabs.lib.db import Db
from wklabs.lib.delivery import RouteRepo
from wklabs.lib.settings import Settings
from wklabs.lib.sync import SyncEngine
from wklabs.lib.users import TgUserRepo

WK1 = "07fff792-eea6-4699-9053-46f67ef92656"
WK2 = "27f9b9f5-c9ba-4412-93f4-12a776853982"
BOT_ID = 999


def tg_user(id: int, name: str = "u", is_bot: bool = False) -> User:
    return User(id=id, is_bot=is_bot, first_name=name, username=f"{name}{id}")


def chat_info(
    chat_id: int,
    *,
    type: str = "supergroup",
    title: str = "WK",
    is_forum: bool = True,
    can_send: bool = True,
) -> ChatFullInfo:
    return ChatFullInfo(
        id=chat_id,
        type=type,
        title=title,
        is_forum=is_forum,
        accent_color_id=0,
        max_reaction_count=3,
        accepted_gift_types=AcceptedGiftTypes(
            unlimited_gifts=False,
            limited_gifts=False,
            unique_gifts=False,
            premium_subscription=False,
            gifts_from_channels=False,
        ),
        permissions=ChatPermissions(can_send_messages=can_send, can_manage_topics=False),
    )


def me_admin(topics: bool = True) -> ChatMemberAdministrator:
    return ChatMemberAdministrator(
        user=tg_user(BOT_ID, "bot", True),
        can_be_edited=False,
        is_anonymous=False,
        can_manage_chat=True,
        can_delete_messages=True,
        can_manage_video_chats=False,
        can_restrict_members=False,
        can_promote_members=False,
        can_change_info=False,
        can_invite_users=False,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
        can_pin_messages=True,
        can_manage_topics=topics,
    )


def me_member() -> ChatMemberMember:
    return ChatMemberMember(user=tg_user(BOT_ID, "bot", True))


def me_left() -> ChatMemberLeft:
    return ChatMemberLeft(user=tg_user(BOT_ID, "bot", True))


class FakeBot:
    """Just enough of aiogram.Bot for handlers, TopicManager and Notifier."""

    def __init__(self) -> None:
        self.id = BOT_ID
        self.sent: list[tuple[int, int | None, str]] = []
        self.topics: list[tuple[int, str]] = []
        self.renamed: list[tuple[int, int, str]] = []
        self.chats: dict[int, ChatFullInfo] = {}
        self.members: dict[tuple[int, int], ChatMember] = {}
        self.fail: dict[int, Exception] = {}  # chat_id → raised by send_message
        self._thread = 6

    async def send_message(self, chat_id: int, text: str, **kw: Any) -> SimpleNamespace:
        if chat_id in self.fail:
            raise self.fail[chat_id]
        self.sent.append((chat_id, kw.get("message_thread_id"), text))
        return SimpleNamespace(message_id=len(self.sent))

    async def create_forum_topic(self, chat_id: int, name: str, **kw: Any) -> SimpleNamespace:
        self._thread += 1
        self.topics.append((chat_id, name))
        return SimpleNamespace(message_thread_id=self._thread)

    async def edit_forum_topic(self, chat_id: int, message_thread_id: int, name: str) -> None:
        self.renamed.append((chat_id, message_thread_id, name))

    async def get_chat(self, chat_id: int) -> ChatFullInfo:
        if chat_id not in self.chats:
            raise TelegramBadRequest(SendMessage(chat_id=chat_id, text=""), "chat not found")
        return self.chats[chat_id]

    async def get_chat_member(self, chat_id: int, user_id: int) -> ChatMember:
        m = self.members.get((chat_id, user_id))
        if m is None:
            if user_id == self.id:
                raise TelegramForbiddenError(SendMessage(chat_id=chat_id, text=""), "kicked")
            return ChatMemberLeft(user=tg_user(user_id))
        return m


def forbidden(chat_id: int) -> TelegramForbiddenError:
    return TelegramForbiddenError(
        SendMessage(chat_id=chat_id, text=""), "Forbidden: bot was kicked from the supergroup chat"
    )


def bad_request(chat_id: int, text: str) -> TelegramBadRequest:
    return TelegramBadRequest(SendMessage(chat_id=chat_id, text=""), f"Bad Request: {text}")


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
        db,
        b,
        routes=routes,
        chats=chats,
        accounts=accounts,
        users=users,
        topics=topics,
        tz="Europe/Kyiv",
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
        bot_username="wklabs_bot",
    )


def ident(wk_id: str = WK1, username: str = "Vitalik", level: int = 39) -> WkIdentity:
    return WkIdentity(wk_id, username, level, "lifetime", 60)
