"""stdout logging (journald-friendly); quiets noisy libraries."""

from __future__ import annotations

import logging


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    for noisy in ("pymongo", "httpx", "httpcore", "aiogram.event", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
