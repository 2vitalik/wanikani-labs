"""Process settings: env vars win, then the `.env` file ($WKLABS_ENV_FILE or repo root).

WaniKani accounts are not configured here — they live in Mongo (`accounts`,
added through the bot or `wklabs accounts add`). The env holds the bot token,
the admin ids and the Fernet key that encrypts account tokens at rest.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# packages/lib/src/wklabs/lib/settings.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[5]
ENV_FILE = Path(os.environ.get("WKLABS_ENV_FILE", REPO_ROOT / ".env"))

AccessPolicy = Literal["open", "approve", "closed"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    bot_token: str = ""  # empty = dry-run (digests to log, no Telegram)
    tg_admin_ids: Annotated[list[int], NoDecode] = []
    access_policy: AccessPolicy = "open"  # open | approve | closed — see T21

    # Fernet key for account tokens at rest (`wklabs gen-key`) — env WKLABS_SECRET_KEY
    wklabs_secret_key: str = ""

    # Mongo
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "wanikani_labs"

    # Scheduling
    tz: str = "Europe/Kyiv"
    sync_interval: int = 300
    subjects_interval: int = 3600
    heartbeat_time: str = "09:00"  # "HH:MM" local, "" = off

    log_level: str = "INFO"

    @field_validator("tg_admin_ids", mode="before")
    @classmethod
    def _parse_ids(cls, v: object) -> list[int]:
        if v is None or v == "":
            return []
        if isinstance(v, str):
            v = v.strip().strip("[]")
            return [int(x) for x in v.replace(";", ",").split(",") if x.strip()]
        if isinstance(v, list):
            return [int(x) for x in v]  # pyright: ignore[reportUnknownVariableType]
        raise TypeError("tg_admin_ids must be a list or comma-separated string")

    @property
    def secret_key(self) -> str:
        return self.wklabs_secret_key

    @property
    def tg_enabled(self) -> bool:
        return bool(self.bot_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()
