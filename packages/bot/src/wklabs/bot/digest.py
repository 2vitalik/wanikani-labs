"""Render a batch of events of one (account, kind) into Telegram HTML messages (pure)."""

from __future__ import annotations

from collections import defaultdict
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from .render.common import (
    chunk,
    grouped,
    miss_detail,
    move_token,
    order_key,
    subject_of,
    when,
)

Json = dict[str, Any]
_subject, _when, _chunk = subject_of, when, chunk


# ---------------------------------------------------------------- reviews
def render_reviews(
    label: str,
    events: list[Json],
    subjects: dict[int, Json],
    tz: ZoneInfo,
    *,
    items: str = "all",
    sort: str = "stage_asc",
    group: bool = True,
) -> list[str]:
    """`items`: all · wrong (only ❌ and SRS drops) · none (header with counts only);
    `sort`/`group`: order of the lines and grouping of same SRS moves."""
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

    # misses first (except in time order), then the chosen order; same moves form a group
    rows: list[tuple[tuple[float, ...], str, str]] = []
    for sid, g in by_subject.items():
        rv = g.get("reviewed")
        mv = g.get("srs_up") or g.get("srs_down")
        ev = rv or mv
        assert ev is not None
        correct = bool(rv["meta"].get("correct")) if rv else None
        bad = (rv is not None and not correct) or "srs_down" in g
        if items == "none" or (items == "wrong" and not bad):
            continue
        if mv:
            fs, ts = mv["meta"].get("from_stage"), mv["meta"].get("to_stage")
        elif rv and not correct:
            fs = ts = 1  # a miss at Apprentice 1 stays there
        else:
            fs = ts = None
        token = move_token(fs, ts) if fs is not None else ("✅" if correct else "•")
        line = _subject(ev, subjects)
        mw = int(rv["meta"].get("meaning_wrong") or 0) if rv else 0
        rw = int(rv["meta"].get("reading_wrong") or 0) if rv else 0
        if rv and not correct:
            line += miss_detail(mw, rw)
        subj = subjects.get(sid) or {}
        key = order_key(
            sort, frm=fs, to=ts, misses=mw + rw, at=ev.get("at"), level=subj.get("level"), sid=sid
        )
        first = () if sort == "time" else (0.0 if bad else 1.0,)
        rows.append(((*first, *key), token, line))
    rows.sort(key=lambda r: r[0])
    lines = grouped([(token, line) for _, token, line in rows], collapse=group)
    if started and items == "all":
        lines.append(
            "📖 lessons: "
            + ", ".join(_subject(e, subjects, level=False) for e in started[:30])
            + (f" … +{len(started) - 30}" if len(started) > 30 else "")
        )
    if unlocked and items == "all":
        lines.append(
            "🔓 unlocked: "
            + ", ".join(_subject(e, subjects, level=False) for e in unlocked[:30])
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
            items = ", ".join(_subject(e, subjects, level=False) for e in evs[:40])
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
    kind: str,
    label: str | None,
    events: list[Json],
    subjects: dict[int, Json],
    tz: ZoneInfo,
    *,
    items: str = "all",
    sort: str = "stage_asc",
    group: bool = True,
) -> list[str]:
    if kind == "subjects":
        return render_subjects(events, subjects, tz)
    if kind == "live":
        return render_reviews(
            label or "?", events, subjects, tz, items=items, sort=sort, group=group
        )
    if kind == "milestones":
        return render_milestones(label or "?", events, subjects, tz)
    return []
