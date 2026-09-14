"""Session summary — final and live — from `Stats` (+ progress matrices for "what changed").

Blocks (T33 §2): header · moves · wrong · wins · lessons · changes · map; each is a
function, switched by the route settings; optional blocks are dropped from the
end when the message would exceed Telegram's limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from wklabs.lib.progress import Matrix, levels_of, pick_levels, total_counts
from wklabs.lib.sessions import BY_USER, Session
from wklabs.lib.stats import Item, Stats

from .common import (
    MAX_LEN,
    STAGE_EMOJI,
    minutes,
    pct,
    quote,
    span,
    stage_short,
    subject_ref,
    when,
)
from .progress import changed_lines, level_lines

Json = dict[str, Any]
MAX_ITEMS = 40
GROUP_WORD = {
    "guru": "→ Guru",
    "master": "→ Master",
    "enlightened": "→ Enlightened",
    "burned": "🔥",
}


@dataclass(slots=True)
class SessionView:
    """Everything the renderer needs, pure data (the notifier fills it)."""

    label: str
    session: Session
    stats: Stats
    subjects: dict[int, Json]
    tz: ZoneInfo
    live: bool = False
    preview: bool = False
    due: int | None = None
    level: int | None = None
    after: Matrix | None = None  # progress matrix now
    before: Matrix | None = None  # …and before the session (reverse_apply)


def item_line(it: Item, subjects: dict[int, Json]) -> str:
    s = subject_ref(it.subject_id, it.subject_type, subjects)
    if it.moved:
        to = it.to_stage if it.to_stage is not None else 0
        s += f" · {stage_short(it.from_stage)} → {STAGE_EMOJI.get(int(to), '')}{stage_short(to)}"
    if it.count and not it.correct:
        s += f" (m{it.meaning_wrong} r{it.reading_wrong})"
    return s


def _refs(ids: list[int], subjects: dict[int, Json], stats: Stats, limit: int = 30) -> str:
    out = ", ".join(
        subject_ref(sid, stats.items[sid].subject_type if sid in stats.items else None, subjects)
        for sid in ids[:limit]
    )
    return out + (f" … +{len(ids) - limit}" if len(ids) > limit else "")


def header(view: SessionView, opts: Json) -> list[str]:
    st, s, tz = view.stats, view.session, view.tz
    icon = "📖" if st.kind == "lessons" else "🧘"
    word = "lessons" if st.kind == "lessons" else "session"
    if view.live:
        time = f"{when(s.started_at, tz)} → … · live · {minutes(s.duration)}"
    else:
        time = f"{span(s.started_at, s.last_at, tz)} ({minutes(s.duration)})"
    first = f"{icon} <b>{escape(view.label)}</b> · {word} {time}"
    if s.closed_by == BY_USER:
        first += " · ⏹"
    if view.preview:
        first += " · <i>preview</i>"
    lines = [first]
    if st.n_items:
        acc = f"{pct(st.acc_items)} (answers {pct(st.acc_answers)})"
        pace = f" · {st.pace:.1f}/min" if st.pace else ""
        lines.append(f"{st.n_items} reviews · ✅ {st.ok} ❌ {st.bad} · {acc}{pace}")
    if opts.get("moves", True) and (st.up or st.down or st.lessons or st.to_group):
        parts = [f"⬆️ {st.up} ⬇️ {st.down}"] if (st.up or st.down) else []
        parts += [f"{GROUP_WORD[g]} {n}" for g, n in st.to_group.items() if g in GROUP_WORD]
        if st.lessons:
            parts.append(f"📖 {len(st.lessons)} lessons")
        if st.unlocked:
            parts.append(f"🔓 {len(st.unlocked)} unlocked")
        lines.append(" · ".join(parts))
    tail: list[str] = []
    if view.due is not None:
        tail.append(f"⏳ due {view.due}")
    if view.after is not None and view.before is not None:
        a, b = total_counts(view.after)["apprentice"], total_counts(view.before)["apprentice"]
        tail.append(f"🩷 apprentice {b} → {a}" if a != b else f"🩷 apprentice {a}")
    if tail:
        lines.append(" · ".join(tail))
    return lines


def block_wrong(view: SessionView, opts: Json) -> str | None:
    items = str(opts.get("items", "wrong"))
    wrong = view.stats.wrong_items
    if items == "none" or not wrong:
        return None
    return quote(
        f"❌ wrong ({len(wrong)})", [item_line(it, view.subjects) for it in wrong[:MAX_ITEMS]]
    )


def block_all(view: SessionView, opts: Json) -> str | None:
    if str(opts.get("items", "wrong")) != "all":
        return None
    ok = [it for it in view.stats.items.values() if it.count and it.correct]
    if not ok:
        return None
    ok.sort(key=lambda it: (it.level or 0, it.subject_id))
    return quote(f"✅ correct ({len(ok)})", [item_line(it, view.subjects) for it in ok[:MAX_ITEMS]])


def block_wins(view: SessionView, opts: Json) -> str | None:
    if not opts.get("wins", True):
        return None
    st = view.stats
    lines: list[str] = []
    for frm, to in st.level_ups:
        lines.append(f"🎉 <b>Level {to}!</b> (was {frm})")
    for kind, lvl in st.level_events:
        word = {
            "level_started": "▶️ level started",
            "level_passed": "✅ level passed",
            "level_completed": "🏁 level completed",
            "level_abandoned": "↩️ level abandoned",
        }.get(kind, kind)
        lines.append(f"{word}: <b>{lvl}</b>")
    if st.burned:
        lines.append(f"🔥 burned: {_refs(st.burned, view.subjects, st)}")
    if st.passed:
        lines.append(f"💜 passed (Guru): {_refs(st.passed, view.subjects, st)}")
    if st.resurrected:
        lines.append(f"🧟 resurrected: {_refs(st.resurrected, view.subjects, st)}")
    return "\n".join(lines) if lines else None


def block_lessons(view: SessionView, opts: Json) -> str | None:
    st = view.stats
    if not opts.get("lessons", True) or not st.lessons:
        return None
    if len(st.lessons) <= 5:
        return f"📖 lessons: {_refs(st.lessons, view.subjects, st)}"
    return quote(
        f"📖 lessons ({len(st.lessons)})",
        [
            subject_ref(sid, st.items[sid].subject_type, view.subjects)
            for sid in st.lessons[:MAX_ITEMS]
        ],
    )


def block_changes(view: SessionView, opts: Json) -> str | None:
    if not opts.get("changes", True) or view.after is None or view.before is None:
        return None
    lines = changed_lines(view.after, view.before)
    return quote("🗺 what changed", lines) if lines else None


def block_map(view: SessionView, opts: Json) -> str | None:
    if not opts.get("map", False) or view.after is None:
        return None
    levels = pick_levels(levels_of(view.after), view.level, str(opts.get("map_levels", "around5")))
    lines = level_lines(
        view.after,
        view.before,
        levels,
        style=str(opts.get("map_style", "emoji")),
        current=view.level,
    )
    return quote("🗺 map", lines, expandable=True, max_lines=60) if lines else None


BLOCKS = (block_wrong, block_all, block_wins, block_lessons, block_changes, block_map)


def render_session(view: SessionView, opts: Json) -> list[str]:
    """One message: header lines + optional blocks, heavy ones dropped if it would not fit."""
    head = "\n".join(header(view, opts))
    if view.live:  # heavy blocks appear on close (T33 §2)
        blocks = [b for b in (block_wrong(view, opts), block_wins(view, opts)) if b]
    else:
        blocks = [b for fn in BLOCKS if (b := fn(view, opts))]
    text = "\n\n".join([head, *blocks])
    while len(text) > MAX_LEN and blocks:
        blocks.pop()
        text = "\n\n".join([head, *blocks])
    return [text]
