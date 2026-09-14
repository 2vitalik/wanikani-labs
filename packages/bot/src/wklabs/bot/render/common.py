"""Shared pieces of every renderer: HTML helpers, emoji palette, chunking (Telegram limits)."""

from __future__ import annotations

from datetime import datetime, timedelta
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from wklabs.lib.resources import SRS_STAGES
from wklabs.lib.subjects import subject_label, subject_url

Json = dict[str, Any]

MAX_LEN = 3900  # Telegram hard limit is 4096
MAX_LINES = 60  # per message before "… +N more"

STAGE_EMOJI = {
    0: "🔒",
    1: "🩷",
    2: "🩷",
    3: "🩷",
    4: "🩷",
    5: "💜",
    6: "💜",
    7: "💙",
    8: "🩵",
    9: "🔥",
}
STAGE_SHORT = {0: "L", 1: "A1", 2: "A2", 3: "A3", 4: "A4", 5: "G1", 6: "G2", 7: "M", 8: "E", 9: "B"}


def stage_name(n: int | None) -> str:
    return SRS_STAGES.get(int(n), str(n)) if n is not None else "?"


def stage_short(n: int | None) -> str:
    return STAGE_SHORT.get(int(n), str(n)) if n is not None else "?"


def link(subject: Json | None, label: str) -> str:
    url = subject_url(subject)
    text = escape(label)
    return f'<a href="{escape(url)}">{text}</a>' if url else text


def subject_ref(sid: int | None, subject_type: str | None, subjects: dict[int, Json]) -> str:
    subj = subjects.get(int(sid)) if sid is not None else None
    return link(subj, subject_label(subj, sid, subject_type))


def subject_of(ev: Json, subjects: dict[int, Json]) -> str:
    return subject_ref(ev.get("subject_id"), ev.get("subject_type"), subjects)


def when(at: datetime, tz: ZoneInfo) -> str:
    return at.astimezone(tz).strftime("%H:%M")


def span(a: datetime, b: datetime, tz: ZoneInfo) -> str:
    return f"{when(a, tz)}–{when(b, tz)}"


def minutes(td: timedelta) -> str:
    total = int(td.total_seconds() // 60)
    if total < 1:
        return "< 1 min"
    if total < 60:
        return f"{total} min"
    return f"{total // 60} h {total % 60:02d} min"


def pct(x: float | None) -> str:
    return f"{round(100 * x)}%" if x is not None else "—"


def quote(title: str, lines: list[str], *, expandable: bool = True, max_lines: int = 40) -> str:
    """`<blockquote expandable>` — the "hidden quote" Telegram folds by default."""
    shown = lines[:max_lines]
    if len(lines) > max_lines:
        shown.append(f"… +{len(lines) - max_lines} more")
    tag = "<blockquote expandable>" if expandable else "<blockquote>"
    body = "\n".join([title, *shown]) if title else "\n".join(shown)
    return f"{tag}{body}</blockquote>"


def chunk(header: str, lines: list[str], footer: str = "") -> list[str]:
    """Split into messages ≤ MAX_LEN; each chunk repeats the header."""
    out: list[str] = []
    buf: list[str] = []
    size = len(header) + 1
    shown = 0
    for ln in lines:
        if shown >= MAX_LINES:
            break
        if size + len(ln) + 1 > MAX_LEN and buf:
            out.append("\n".join([header, *buf]))
            buf, size = [], len(header) + 1
        buf.append(ln)
        size += len(ln) + 1
        shown += 1
    rest = len(lines) - shown
    if rest > 0:
        buf.append(f"… +{rest} more")
    if footer:
        buf.append(footer)
    out.append("\n".join([header, *buf]) if buf else header)
    return out
