"""Render a batch of events of one (account, category) into Telegram HTML messages (pure)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
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


def _stage(n: int | None) -> str:
    return SRS_STAGES.get(int(n), str(n)) if n is not None else "?"


def _link(subject: Json | None, label: str) -> str:
    url = subject_url(subject)
    text = escape(label)
    return f'<a href="{escape(url)}">{text}</a>' if url else text


def _subject(ev: Json, subjects: dict[int, Json]) -> str:
    sid = ev.get("subject_id")
    subj = subjects.get(int(sid)) if sid is not None else None
    return _link(subj, subject_label(subj, sid, ev.get("subject_type")))


def _when(at: datetime, tz: ZoneInfo) -> str:
    return at.astimezone(tz).strftime("%H:%M")


def _chunk(header: str, lines: list[str], footer: str = "") -> list[str]:
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


# ---------------------------------------------------------------- reviews
def render_reviews(
    label: str, events: list[Json], subjects: dict[int, Json], tz: ZoneInfo
) -> list[str]:
    by_subject: dict[int, dict[str, Json]] = defaultdict(dict)
    unlocked: list[Json] = []
    started: list[Json] = []
    for ev in events:
        kind = ev["kind"]
        if kind == "unlocked":
            unlocked.append(ev)
        elif kind == "started":
            started.append(ev)
        elif kind in ("reviewed", "srs_up", "srs_down") and ev.get("subject_id") is not None:
            by_subject[int(ev["subject_id"])][kind] = ev

    n_reviews = sum(
        int(g["reviewed"]["meta"].get("count", 1)) for g in by_subject.values() if "reviewed" in g
    )
    n_ok = sum(
        1 for g in by_subject.values() if "reviewed" in g and g["reviewed"]["meta"].get("correct")
    )
    n_bad = sum(
        1
        for g in by_subject.values()
        if "reviewed" in g and not g["reviewed"]["meta"].get("correct")
    )
    n_up = sum(1 for g in by_subject.values() if "srs_up" in g)
    n_down = sum(1 for g in by_subject.values() if "srs_down" in g)
    at = max(ev["at"] for ev in events)
    parts = [f"📝 <b>{escape(label)}</b> · {_when(at, tz)}"]
    if n_reviews:
        parts.append(f"{n_reviews} reviews: ✅ {n_ok} · ❌ {n_bad} · ⬆️ {n_up} · ⬇️ {n_down}")
    if started:
        parts.append(f"📖 {len(started)} lessons")
    if unlocked:
        parts.append(f"🔓 {len(unlocked)} unlocked")
    header = " — ".join(parts)

    lines: list[str] = []

    # worst first: wrong answers, then SRS drops, then the rest
    def sort_key(item: tuple[int, dict[str, Json]]) -> tuple[int, int]:
        g = item[1]
        wrong = 0 if g.get("reviewed", {}).get("meta", {}).get("correct", True) else 1
        down = 1 if "srs_down" in g else 0
        return (-(wrong + down), item[0])

    for _sid, g in sorted(by_subject.items(), key=sort_key):
        rv = g.get("reviewed")
        mv = g.get("srs_up") or g.get("srs_down")
        ev = rv or mv
        assert ev is not None
        mark = ("✅" if rv["meta"].get("correct") else "❌") if rv else "•"
        s = f"{mark} {_subject(ev, subjects)}"
        if mv:
            fs, ts = mv["meta"].get("from_stage"), mv["meta"].get("to_stage")
            s += f" · {_stage(fs)} → {STAGE_EMOJI.get(int(ts), '')}{_stage(ts)}"
        if rv and not rv["meta"].get("correct"):
            mw, rw = rv["meta"].get("meaning_wrong", 0), rv["meta"].get("reading_wrong", 0)
            s += f" (m{mw} r{rw})"
        lines.append(s)
    if started:
        lines.append(
            "📖 lessons: "
            + ", ".join(_subject(e, subjects) for e in started[:30])
            + (f" … +{len(started) - 30}" if len(started) > 30 else "")
        )
    if unlocked:
        lines.append(
            "🔓 unlocked: "
            + ", ".join(_subject(e, subjects) for e in unlocked[:30])
            + (f" … +{len(unlocked) - 30}" if len(unlocked) > 30 else "")
        )
    return _chunk(header, lines)


# ------------------------------------------------------------- milestones
def render_milestones(
    label: str, events: list[Json], subjects: dict[int, Json], tz: ZoneInfo
) -> list[str]:
    at = max(ev["at"] for ev in events)
    header = f"🏆 <b>{escape(label)}</b> · {_when(at, tz)}"
    lines: list[str] = []
    groups: dict[str, list[Json]] = defaultdict(list)
    for ev in events:
        groups[ev["kind"]].append(ev)
    for ev in groups.get("user_level", []):
        lines.append(
            f"🎉 <b>Level {ev['meta'].get('to_level')}!</b> (was {ev['meta'].get('from_level')})"
        )
    for kind, label in (
        ("level_started", "▶️ level started"),
        ("level_passed", "✅ level passed"),
        ("level_completed", "🏁 level completed"),
        ("level_abandoned", "↩️ level abandoned"),
    ):
        for ev in groups.get(kind, []):
            lines.append(f"{label}: <b>{ev['meta'].get('level')}</b>")
    for ev in groups.get("reset", []):
        lines.append(
            f"♻️ reset: level {ev['meta'].get('original_level')} → {ev['meta'].get('target_level')}"
        )
    for kind, label in (
        ("burned", "🔥 burned"),
        ("passed", "💜 passed (Guru)"),
        ("resurrected", "🧟 resurrected"),
    ):
        evs = groups.get(kind, [])
        if evs:
            items = ", ".join(_subject(e, subjects) for e in evs[:40])
            more = f" … +{len(evs) - 40}" if len(evs) > 40 else ""
            lines.append(f"{label} ({len(evs)}): {items}{more}")
    return _chunk(header, lines)


# ---------------------------------------------------------------- subjects
def render_subjects(events: list[Json], subjects: dict[int, Json], tz: ZoneInfo) -> list[str]:
    at = max(ev["at"] for ev in events)
    by_kind: dict[str, list[Json]] = defaultdict(list)
    for ev in events:
        by_kind[ev["kind"]].append(ev)
    counts = " · ".join(f"{k.removeprefix('subject_')} {len(v)}" for k, v in by_kind.items())
    header = f"📚 <b>subjects</b> · {_when(at, tz)} — {counts}"
    lines: list[str] = []
    for ev in by_kind.get("subject_new", []):
        lines.append(f"🆕 {_subject(ev, subjects)}")
    for ev in by_kind.get("subject_hidden", []):
        lines.append(f"🙈 {_subject(ev, subjects)}")
    for ev in by_kind.get("subject_updated", []):
        changed = ", ".join(ev["meta"].get("changed", []))
        lines.append(f"✏️ {_subject(ev, subjects)} — {escape(changed)}")
    return _chunk(header, lines)


def render(
    category: str,
    label: str | None,
    events: list[Json],
    subjects: dict[int, Json],
    tz: ZoneInfo,
) -> list[str]:
    if category == "subjects":
        return render_subjects(events, subjects, tz)
    if category == "reviews":
        return render_reviews(label or "?", events, subjects, tz)
    if category == "milestones":
        return render_milestones(label or "?", events, subjects, tz)
    return []
