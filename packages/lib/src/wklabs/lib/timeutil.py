"""Timestamp helpers. WaniKani sends ISO-8601 UTC with microseconds (`...Z`)."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_ts(value: str | None) -> datetime | None:
    """`2026-03-28T21:33:56.948983Z` -> aware UTC datetime (None passes through)."""
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def fmt_ts(dt: datetime | None) -> str:
    """Back to the WaniKani wire format (microseconds, `Z`)."""
    if dt is None:
        return ""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
