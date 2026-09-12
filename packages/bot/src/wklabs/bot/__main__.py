"""Entry point: `python -m wklabs.bot` / `wklabs-bot`.

Start order (journald-greppable): ping Mongo → indexes → bot → scheduler
(first global+account sync within seconds) → polling. Accounts live in Mongo
(`/accounts` in the bot, `wklabs accounts …`); the bot runs fine with none.
Without BOT_TOKEN: dry-run (polls, logs digests, no Telegram).
"""

from __future__ import annotations

import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.pymongo import PyMongoStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
)

from wklabs.lib.accounts import AccountRepo
from wklabs.lib.chats import ChatRepo
from wklabs.lib.crypto import CipherError, TokenCipher
from wklabs.lib.db import TG_FSM, Db
from wklabs.lib.delivery import RouteRepo
from wklabs.lib.logging_setup import setup_logging
from wklabs.lib.settings import get_settings
from wklabs.lib.sync import SyncEngine
from wklabs.lib.users import TgUserRepo

from .context import AppContext
from .handlers import ROUTERS
from .middleware import ChatMiddleware, UserMiddleware
from .notifier import Notifier
from .scheduler import build_scheduler
from .topics import TopicManager

log = logging.getLogger("wklabs.bot")

PRIVATE_COMMANDS = [
    BotCommand(command="accounts", description="your WaniKani accounts"),
    BotCommand(command="chats", description="chats and forums I post to"),
    BotCommand(command="status", description="levels, reviews due, last sync"),
    BotCommand(command="help", description="how it works"),
]
GROUP_COMMANDS = [
    BotCommand(command="setup", description="deliver digests to this chat"),
    BotCommand(command="status", description="levels, reviews due, last sync"),
    BotCommand(command="ping", description="am I alive?"),
]
ADMIN_COMMANDS = [
    *PRIVATE_COMMANDS,
    BotCommand(command="admin", description="users, accounts, sync"),
    BotCommand(command="sync", description="poll now"),
    BotCommand(command="sync_full", description="full refetch"),
]


async def run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    try:
        cipher = TokenCipher.from_settings(settings)
    except CipherError as exc:
        raise SystemExit(str(exc)) from exc

    db = Db.from_settings(settings)
    await db.ping()
    await db.ensure_indexes()
    accounts = AccountRepo(db, cipher)
    users = TgUserRepo(db, admin_ids=settings.tg_admin_ids, policy=settings.access_policy)
    chats, routes = ChatRepo(db), RouteRepo(db)
    await chats.normalize_legacy()
    active = await accounts.list()
    log.info(
        "MongoDB connected: db=%s · active accounts=%s · policy=%s · admins=%s",
        settings.mongo_db,
        [a.key for a in active],
        settings.access_policy,
        settings.tg_admin_ids,
    )

    bot: Bot | None = None
    if settings.tg_enabled:
        bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    else:
        log.warning("BOT_TOKEN not set → dry-run (no Telegram at all, digests go to the log)")

    engine = SyncEngine(db, accounts)
    topics = TopicManager(bot, chats, routes, accounts)
    notifier = Notifier(
        db,
        bot,
        routes=routes,
        chats=chats,
        accounts=accounts,
        users=users,
        topics=topics,
        tz=settings.tz,
    )
    ctx = AppContext(
        settings=settings,
        db=db,
        engine=engine,
        accounts=accounts,
        users=users,
        chats=chats,
        routes=routes,
        topics=topics,
        notifier=notifier,
        bot=bot,
    )

    sched = build_scheduler(ctx)
    sched.start()
    log.info(
        "scheduler started: accounts every %ss, global every %ss",
        settings.sync_interval,
        settings.subjects_interval,
    )

    try:
        if bot is None:
            stop = asyncio.Event()
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, stop.set)
            log.info("dry-run loop running; Ctrl+C to stop")
            await stop.wait()
        else:
            storage = PyMongoStorage(
                client=db.client, db_name=settings.mongo_db, collection_name=TG_FSM
            )
            dp = Dispatcher(storage=storage)
            seen = ChatMiddleware(ctx)  # first: registers the chat even for blocked users
            for observer in (dp.message, dp.callback_query, dp.my_chat_member):
                observer.outer_middleware(seen)
                observer.outer_middleware(UserMiddleware(ctx))
            for r in ROUTERS:
                dp.include_router(r)
            dp["ctx"] = ctx
            me = await bot.get_me()
            ctx.bot_username = me.username or ""
            await bot.set_my_commands(PRIVATE_COMMANDS, scope=BotCommandScopeAllPrivateChats())
            await bot.set_my_commands(GROUP_COMMANDS, scope=BotCommandScopeAllGroupChats())
            for admin_id in settings.tg_admin_ids:
                try:
                    await bot.set_my_commands(
                        ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id)
                    )
                except Exception as exc:  # admin never opened the bot yet
                    log.info("admin commands for %s not set: %s", admin_id, exc)
            log.info("polling as @%s (id=%s)", me.username, me.id)
            await dp.start_polling(bot, handle_signals=True)
    finally:
        sched.shutdown(wait=False)
        await engine.aclose()
        if bot is not None:
            await bot.session.close()
        await db.close()
        log.info("bye")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
