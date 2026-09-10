"""Entry point: `python -m wklabs.bot` / `wklabs-bot`.

Start order (journald-greppable): ping Mongo → indexes → bot → topics →
scheduler (first global+account sync within seconds) → polling.
Without BOT_TOKEN: dry-run (polls, logs digests). With a token but no
TG_FORUM_CHAT_ID: bootstrap — answers /start (chat/thread/user ids), logs digests.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from wklabs.lib.db import Db
from wklabs.lib.logging_setup import setup_logging
from wklabs.lib.settings import get_settings
from wklabs.lib.sync import SyncEngine

from .context import AppContext
from .handlers import public, router
from .notifier import Notifier
from .scheduler import build_scheduler
from .topics import TopicManager

log = logging.getLogger("wklabs.bot")


async def run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    if not settings.accounts:
        raise SystemExit("no WaniKani accounts configured (WK_TOKEN__<NAME>)")

    db = Db.from_settings(settings)
    await db.ping()
    await db.ensure_indexes()
    log.info("MongoDB connected: db=%s · accounts=%s", settings.mongo_db, settings.accounts)

    bot: Bot | None = None
    if settings.tg_enabled:
        bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        if not settings.forum_enabled:
            log.warning(
                "TG_FORUM_CHAT_ID not set → bootstrap mode: /start answers (shows chat id), "
                "digests go to the log"
            )
    else:
        log.warning("BOT_TOKEN not set → dry-run (no Telegram at all, digests go to the log)")

    engine = SyncEngine(db, settings.wk_token)
    topics = TopicManager(db, settings.tg_forum_chat_id, settings.accounts)
    notifier = Notifier(db, bot, topics, settings.tz, settings.tg_forum_chat_id)
    ctx = AppContext(
        settings=settings, db=db, engine=engine, topics=topics, notifier=notifier, bot=bot
    )

    if bot is not None:
        try:
            created = await topics.ensure(bot)
            log.info("forum topics ready (%d created): %s", len(created), sorted(topics.threads))
        except Exception:
            log.exception("could not ensure forum topics (is the bot admin with Manage Topics?)")

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
            dp = Dispatcher()
            dp.include_router(public)
            dp.include_router(router)
            dp["ctx"] = ctx
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="am I alive? shows your id"),
                    BotCommand(command="status", description="last sync, levels, reviews due"),
                    BotCommand(command="sync", description="poll now"),
                    BotCommand(command="sync_full", description="full refetch"),
                    BotCommand(command="topics", description="ensure forum topics"),
                    BotCommand(command="help", description="help"),
                ]
            )
            me = await bot.get_me()
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
