"""Statistics of a window of events (a session, a day, a week): one code for every report.

Pure: `window_stats(events, subjects)` folds stored event docs into `Stats`;
`subjects` (id → doc with `level`/`type`) is only needed for per-level and
per-type breakdowns and may be partial.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Any

Json = dict[str, Any]

# srs stage → group (T33 §3.1)
GROUP_OF: dict[int, str] = {
    0: "lesson",
    1: "apprentice",
    2: "apprentice",
    3: "apprentice",
    4: "apprentice",
    5: "guru",
    6: "guru",
    7: "master",
    8: "enlightened",
    9: "burned",
}
READING_TYPES = ("kanji", "vocabulary")  # answer a reading question too


def group_of(stage: int | None) -> str:
    return GROUP_OF.get(int(stage), "?") if stage is not None else "locked"


@dataclass(slots=True)
class Item:
    """One subject touched in the window: its review result and/or SRS move."""

    subject_id: int
    subject_type: str | None
    level: int | None
    count: int = 0  # reviews (Σ meta.count); 0 = only moved / started
    meaning_wrong: int = 0
    reading_wrong: int = 0
    correct: bool | None = None  # None = not reviewed in the window
    from_stage: int | None = None
    to_stage: int | None = None
    percentage: int | None = None
    started: bool = False
    unlocked: bool = False
    burned: bool = False
    passed: bool = False
    resurrected: bool = False

    @property
    def wrong(self) -> bool:
        return self.correct is False or (
            self.from_stage is not None
            and self.to_stage is not None
            and self.to_stage < self.from_stage
        )

    @property
    def moved(self) -> bool:
        return self.from_stage is not None and self.to_stage is not None


@dataclass(slots=True)
class Stats:
    first_at: datetime | None = None
    last_at: datetime | None = None
    n_items: int = 0  # distinct reviewed subjects
    n_reviews: int = 0  # Σ count
    ok: int = 0  # items with no wrong answer
    bad: int = 0
    meaning_wrong: int = 0
    reading_wrong: int = 0
    answers: int = 0  # meaning + reading answers given
    answers_wrong: int = 0
    up: int = 0
    down: int = 0
    to_group: dict[str, int] = field(default_factory=dict)  # guru/master/enlightened/burned
    by_type: dict[str, tuple[int, int]] = field(default_factory=dict)  # type → (n, bad)
    by_level: dict[int, tuple[int, int]] = field(default_factory=dict)  # level → (n, bad)
    lessons: list[int] = field(default_factory=list)  # started subject ids, in order
    unlocked: list[int] = field(default_factory=list)
    passed: list[int] = field(default_factory=list)
    burned: list[int] = field(default_factory=list)
    resurrected: list[int] = field(default_factory=list)
    level_ups: list[tuple[int | None, int | None]] = field(default_factory=list)
    level_events: list[tuple[str, int | None]] = field(default_factory=list)
    resets: int = 0
    items: dict[int, Item] = field(default_factory=dict)
    longest_pause: timedelta | None = None
    n_instants: int = 0

    @property
    def duration(self) -> timedelta:
        if self.first_at is None or self.last_at is None:
            return timedelta(0)
        return self.last_at - self.first_at

    @property
    def acc_items(self) -> float | None:
        return self.ok / self.n_items if self.n_items else None

    @property
    def acc_answers(self) -> float | None:
        return (self.answers - self.answers_wrong) / self.answers if self.answers else None

    @property
    def pace(self) -> float | None:
        """Reviewed items per minute (None for a single instant)."""
        minutes = self.duration.total_seconds() / 60
        return self.n_items / minutes if minutes >= 1 and self.n_items else None

    @property
    def kind(self) -> str:
        if self.n_items and self.lessons:
            return "mixed"
        if self.n_items:
            return "reviews"
        if self.lessons:
            return "lessons"
        return "none"

    @property
    def wrong_items(self) -> list[Item]:
        return sorted(
            (it for it in self.items.values() if it.wrong),
            key=lambda it: (-(it.meaning_wrong + it.reading_wrong), it.level or 0, it.subject_id),
        )

    def to_doc(self) -> Json:
        """Compact cache for `sessions.stats` (lists of ids only, no per-item detail)."""
        return {
            "n_items": self.n_items,
            "n_reviews": self.n_reviews,
            "ok": self.ok,
            "bad": self.bad,
            "answers": self.answers,
            "answers_wrong": self.answers_wrong,
            "up": self.up,
            "down": self.down,
            "to_group": dict(self.to_group),
            "lessons": len(self.lessons),
            "unlocked": len(self.unlocked),
            "burned": len(self.burned),
            "passed": len(self.passed),
            "level_ups": [list(x) for x in self.level_ups],
            "kind": self.kind,
            "duration_s": int(self.duration.total_seconds()),
            "n_instants": self.n_instants,
        }


def _level(subjects: dict[int, Json], sid: int | None) -> int | None:
    if sid is None:
        return None
    s = subjects.get(sid)
    lvl = s.get("level") if s else None
    return int(lvl) if lvl is not None else None


def window_stats(events: list[Json], subjects: dict[int, Json] | None = None) -> Stats:
    subjects = subjects or {}
    st = Stats()
    items: dict[int, Item] = {}
    instants: set[datetime] = set()

    def item(ev: Json) -> Item | None:
        sid = ev.get("subject_id")
        if sid is None:
            return None
        sid = int(sid)
        it = items.get(sid)
        if it is None:
            it = items[sid] = Item(sid, ev.get("subject_type"), _level(subjects, sid))
        return it

    for ev in sorted(events, key=lambda e: e["at"]):
        kind = str(ev.get("kind"))
        meta = ev.get("meta") or {}
        at: datetime = ev["at"]
        if kind in ("reviewed", "started"):
            instants.add(at)
        if st.first_at is None or at < st.first_at:
            st.first_at = at
        if st.last_at is None or at > st.last_at:
            st.last_at = at
        match kind:
            case "reviewed":
                it = item(ev)
                if it is None:
                    continue
                n = int(meta.get("count") or 1)
                mw, rw = int(meta.get("meaning_wrong") or 0), int(meta.get("reading_wrong") or 0)
                it.count += n
                it.meaning_wrong += mw
                it.reading_wrong += rw
                it.correct = (it.correct is not False) and bool(meta.get("correct", mw + rw == 0))
                it.percentage = meta.get("percentage")
            case "srs_up" | "srs_down":
                it = item(ev)
                if it is None:
                    continue
                fs, ts = meta.get("from_stage"), meta.get("to_stage")
                if it.from_stage is None:
                    it.from_stage = fs
                it.to_stage = ts
            case "started":
                it = item(ev)
                if it is not None:
                    it.started = True
                    st.lessons.append(it.subject_id)
            case "unlocked":
                it = item(ev)
                if it is not None:
                    it.unlocked = True
                    st.unlocked.append(it.subject_id)
            case "passed":
                it = item(ev)
                if it is not None:
                    it.passed = True
                    st.passed.append(it.subject_id)
            case "burned":
                it = item(ev)
                if it is not None:
                    it.burned = True
                    st.burned.append(it.subject_id)
            case "resurrected":
                it = item(ev)
                if it is not None:
                    it.resurrected = True
                    st.resurrected.append(it.subject_id)
            case "user_level":
                st.level_ups.append((meta.get("from_level"), meta.get("to_level")))
            case "level_started" | "level_passed" | "level_completed" | "level_abandoned":
                st.level_events.append((kind, meta.get("level")))
            case "reset":
                st.resets += 1

    by_type: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_level: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for it in items.values():
        if it.count:
            st.n_items += 1
            st.n_reviews += it.count
            wrong = it.meaning_wrong + it.reading_wrong
            if it.correct:
                st.ok += 1
            else:
                st.bad += 1
            st.meaning_wrong += it.meaning_wrong
            st.reading_wrong += it.reading_wrong
            st.answers += it.count * (2 if it.subject_type in READING_TYPES else 1) + wrong
            st.answers_wrong += wrong
            t = it.subject_type or "?"
            by_type[t][0] += 1
            by_type[t][1] += 0 if it.correct else 1
            if it.level is not None:
                by_level[it.level][0] += 1
                by_level[it.level][1] += 0 if it.correct else 1
        if it.moved:
            assert it.from_stage is not None and it.to_stage is not None
            if it.to_stage > it.from_stage:
                st.up += 1
                g_from, g_to = group_of(it.from_stage), group_of(it.to_stage)
                if g_to != g_from and g_to in ("guru", "master", "enlightened", "burned"):
                    st.to_group[g_to] = st.to_group.get(g_to, 0) + 1
            elif it.to_stage < it.from_stage:
                st.down += 1
    st.by_type = {k: (v[0], v[1]) for k, v in by_type.items()}
    st.by_level = {k: (v[0], v[1]) for k, v in sorted(by_level.items())}
    st.items = items
    ordered = sorted(instants)
    st.n_instants = len(ordered)
    if len(ordered) > 1:
        st.longest_pause = max(b - a for a, b in pairwise(ordered))
    return st
