"""Shared pieces of every renderer: HTML helpers, stage/type tokens, chunking (Telegram limits)."""

from __future__ import annotations

from datetime import datetime, timedelta
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from wklabs.lib.subjects import level_tag, subject_label, subject_url, type_mark

Json = dict[str, Any]

MAX_LEN = 3900  # Telegram hard limit is 4096
MAX_LINES = 60  # per message before "… +N more"

# SRS stage as emoji + one cell: inside <code> a column of these lines up (T38)
STAGE_TOKEN = {
    0: "🔒 ",
    1: "🩷1",
    2: "🩷2",
    3: "🩷3",
    4: "🩷4",
    5: "💜1",
    6: "💜2",
    7: "💙 ",
    8: "🩵 ",
    9: "🔥 ",
}


def stage_token(n: int | None) -> str:
    return STAGE_TOKEN.get(int(n), f"?{n}") if n is not None else " ? "


def move_token(frm: int | None, to: int | None) -> str:
    """`🩷3 → 🩷4`: stages in monospace (fixed width), the arrow in the normal font."""
    return f"<code>{stage_token(frm)}</code> → <code>{stage_token(to)}</code>"


def order_key(
    sort: str,
    *,
    frm: int | None,
    to: int | None,
    misses: int,
    at: datetime | None,
    level: int | None,
    sid: int,
) -> tuple[float, ...]:
    """Sort key of an item line: stage ↑ (default) · stage ↓ · misses · time."""
    f = frm if frm is not None else -1
    t = to if to is not None else -1
    if sort == "stage_desc":
        return (-f, -t, level or 0, sid)
    if sort == "misses":
        return (-misses, f, t, level or 0, sid)
    if sort == "time":
        return (at.timestamp() if at else 0.0, sid)
    return (f, t, level or 0, sid)


def miss_detail(meaning_wrong: int, reading_wrong: int) -> str:
    """` (m1 r2)` with zero parts dropped."""
    parts = [
        f"m{meaning_wrong}" if meaning_wrong else "",
        f"r{reading_wrong}" if reading_wrong else "",
    ]
    parts = [p for p in parts if p]
    return f" ({' '.join(parts)})" if parts else ""


def link(subject: Json | None, label: str) -> str:
    url = subject_url(subject)
    text = escape(label)
    return f'<a href="{escape(url)}">{text}</a>' if url else text


def subject_ref(
    sid: int | None, subject_type: str | None, subjects: dict[int, Json], *, level: bool = True
) -> str:
    """`🔴 L12 <a>漢 · Chinese</a>` — type mark and level outside the link; `level=False` for
    inline comma lists."""
    subj = subjects.get(int(sid)) if sid is not None else None
    typ = (subj or {}).get("type") or subject_type
    head = type_mark(typ)
    if level:
        head += f" {level_tag((subj or {}).get('level'))}"
    return f"{head} {link(subj, subject_label(subj, sid, subject_type))}"


def subject_of(ev: Json, subjects: dict[int, Json], *, level: bool = True) -> str:
    return subject_ref(ev.get("subject_id"), ev.get("subject_type"), subjects, level=level)


def grouped(rows: list[tuple[str, str]], *, collapse: bool = True) -> list[str]:
    """Rows are (token, line) in display order. Rows sharing a token collapse under one header
    `token · n` (placed where the token first appears); a lone row keeps its token inline.
    `collapse=False`: every row inline (T38 §1, T40)."""
    if not collapse:
        return [f"{token} {line}" for token, line in rows]
    buckets: dict[str, list[str]] = {}
    for token, line in rows:
        buckets.setdefault(token, []).append(line)
    out: list[str] = []
    for token, lines in buckets.items():
        if len(lines) == 1:
            out.append(f"{token} {lines[0]}")
        else:
            out.append(f"{token} · {len(lines)}")
            out.extend(lines)
    return out


def tg_len(text: str) -> int:
    """Telegram counts UTF-16 units: every astral character (emoji) is two."""
    return len(text) + sum(1 for ch in text if ord(ch) > 0xFFFF)


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
