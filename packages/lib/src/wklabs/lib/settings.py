"""Process settings: env vars win, then the `.env` file ($WKLABS_ENV_FILE or repo root).

Accounts are declared as `WK_TOKEN__<KEY>=<token>`; the key (lower-cased)
becomes the account name used everywhere (`main`, `light`, ...).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# packages/lib/src/wklabs/lib/settings.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[5]
ENV_FILE = Path(os.environ.get("WKLABS_ENV_FILE", REPO_ROOT / ".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # WaniKani — account key -> API token (WK_TOKEN__MAIN=..., WK_TOKEN__LIGHT=...)
    wk_token: dict[str, str] = {}

    # Telegram
    bot_token: str = ""  # empty = dry-run (digests to log)
    tg_forum_chat_id: int | None = None
    tg_admin_ids: Annotated[list[int], NoDecode] = []

    # Mongo
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "wanikani_labs"

    # Scheduling
    tz: str = "Europe/Kyiv"
    sync_interval: int = 300
    subjects_interval: int = 3600
    heartbeat_time: str = "09:00"  # "HH:MM" local, "" = off

    log_level: str = "INFO"

    @field_validator("tg_forum_chat_id", mode="before")
    @classmethod
    def _empty_is_none(cls, v: object) -> object:
        return None if v == "" else v

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

    @field_validator("wk_token", mode="before")
    @classmethod
    def _lower_keys(cls, v: object) -> dict[str, str]:
        if not v:
            return {}
        if isinstance(v, dict):
            return {str(k).lower(): str(t) for k, t in v.items() if t}  # pyright: ignore[reportUnknownVariableType]
        raise TypeError("wk_token must be a mapping")

    @property
    def accounts(self) -> list[str]:
        return sorted(self.wk_token)

    @property
    def tg_enabled(self) -> bool:
        """Telegram polling (commands) — token is enough; digests also need the forum."""
        return bool(self.bot_token)

    @property
    def forum_enabled(self) -> bool:
        return bool(self.bot_token and self.tg_forum_chat_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
