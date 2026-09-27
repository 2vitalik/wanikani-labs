"""Progress map data: level x type x SRS stage of an account, and the state *before* a window.

`stage_matrix` reads current `assignments` + `subjects`; `reverse_apply` undoes
the window's `srs_up/srs_down/unlocked` events on it, which gives the exact
earlier matrix without snapshots (T33 §3.1). Rendering lives in the bot.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .db import Db
from .stats import GROUP_OF

Json = dict[str, Any]
LOCKED = -1  # pseudo stage: no assignment yet
Matrix = dict[tuple[int, str, int], int]  # (level, subject type, stage) → n
SubjectIndex = dict[int, tuple[int, str]]  # subject id → (level, type)

GROUPS: tuple[tuple[str, str], ...] = (
    ("locked", "🔒"),
    ("lesson", "🥚"),  # unlocked, lesson not taken yet
    ("apprentice", "🩷"),
    ("guru", "💜"),
    ("master", "💙"),
    ("enlightened", "🩵"),
    ("burned", "🔥"),
)
GROUP_EMOJI: dict[str, str] = dict(GROUPS)
GROUP_ORDER = [g for g, _ in GROUPS]
TYPES = ("radical", "kanji", "vocabulary", "kana_vocabulary")

# /progress and map-block options (values cycle in this order); T33 §3.2
LEVELS_CHOICES: tuple[tuple[str, str], ...] = (
    ("around3", "now-3"),
    ("around5", "now-5"),
    ("around10", "now-10"),
    ("to_current", "1…now"),
    ("all", "all"),
)
STYLE_CHOICES: tuple[tuple[str, str], ...] = (
    ("emoji", "emoji"),
    ("counts", "counts"),
    ("both", "both"),
)
SORT_CHOICES: tuple[tuple[str, str], ...] = (("asc", "↑"), ("desc", "↓"))
FILTER_CHOICES: tuple[tuple[str, str], ...] = (
    ("all", "all"),
    ("apprentice", "apprentice"),
    ("changed", "changed"),
)
GROUP_CHOICES: tuple[tuple[str, str], ...] = (("level", "level"), ("stage", "stage"))
DIFF_CHOICES: tuple[tuple[str, str], ...] = (
    ("session", "session"),
    ("day", "day"),
    ("week", "week"),
    ("off", "off"),
)
PROGRESS_OPTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "levels": LEVELS_CHOICES,
    "sort": SORT_CHOICES,
    "group": GROUP_CHOICES,
    "filter": FILTER_CHOICES,
    "style": STYLE_CHOICES,
    "diff": DIFF_CHOICES,
}
DEFAULT_PROGRESS: dict[str, str] = {
    "levels": "around5",
    "sort": "asc",
    "group": "level",
    "filter": "all",
    "style": "emoji",
    "diff": "session",
}


def group_of_stage(stage: int) -> str:
    return "locked" if stage == LOCKED else GROUP_OF.get(stage, "?")


def normalize_options(opts: Json | None) -> dict[str, str]:
    out = dict(DEFAULT_PROGRESS)
    for key, value in (opts or {}).items():
        if key in PROGRESS_OPTIONS and any(value == v for v, _ in PROGRESS_OPTIONS[key]):
            out[key] = str(value)
    return out


def next_option(key: str, current: str) -> str:
    values = [v for v, _ in PROGRESS_OPTIONS[key]]
    try:
        return values[(values.index(current) + 1) % len(values)]
    except ValueError:
        return values[0]


def option_label(key: str, value: str) -> str:
    return next((label for v, label in PROGRESS_OPTIONS[key] if v == value), value)


async def subject_index(db: Db, ids: set[int] | None = None) -> SubjectIndex:
    """id → (level, type) for visible subjects (all of them, or just `ids`)."""
    q: Json = {"hidden_at": None}
    if ids is not None:
        if not ids:
            return {}
        q = {"_id": {"$in": sorted(ids)}}
    out: SubjectIndex = {}
    async for d in db.col("subjects").find(q, {"level": 1, "type": 1}):
        if d.get("level") is not None and d.get("type"):
            out[int(d["_id"])] = (int(d["level"]), str(d["type"]))
    return out


async def stage_matrix(db: Db, account: str, index: SubjectIndex | None = None) -> Matrix:
    index = index if index is not None else await subject_index(db)
    m: Matrix = {}
    for _sid, (lvl, typ) in index.items():
        m[(lvl, typ, LOCKED)] = m.get((lvl, typ, LOCKED), 0) + 1
    async for a in db.current("assignments").find(
        {"account": account, "hidden": False}, {"subject_id": 1, "srs_stage": 1}
    ):
        meta = index.get(int(a["subject_id"]))
        if meta is None or a.get("srs_stage") is None:
            continue
        lvl, typ = meta
        stage = int(a["srs_stage"])
        m[(lvl, typ, LOCKED)] = m.get((lvl, typ, LOCKED), 0) - 1
        m[(lvl, typ, stage)] = m.get((lvl, typ, stage), 0) + 1
    return m


def reverse_apply(matrix: Matrix, events: list[Json], index: SubjectIndex) -> Matrix:
    """The matrix before these events happened (undo srs moves and unlocks; counts only)."""
    m = dict(matrix)

    def undo(lvl: int, typ: str, frm: int, to: int) -> None:
        """One subject went frm → to inside the window: put it back."""
        m[(lvl, typ, to)] = m.get((lvl, typ, to), 0) - 1
        m[(lvl, typ, frm)] = m.get((lvl, typ, frm), 0) + 1

    for ev in events:
        sid = ev.get("subject_id")
        meta_s = index.get(int(sid)) if sid is not None else None
        if meta_s is None:
            continue
        lvl, typ = meta_s
        meta = ev.get("meta") or {}
        kind = ev.get("kind")
        if kind in ("srs_up", "srs_down"):
            fs, ts = meta.get("from_stage"), meta.get("to_stage")
            if fs is not None and ts is not None:
                undo(lvl, typ, int(fs), int(ts))
        elif kind == "unlocked":
            undo(lvl, typ, LOCKED, 0)
    return m


def levels_of(matrix: Matrix) -> list[int]:
    return sorted({lvl for (lvl, _t, _s) in matrix})


def group_counts(
    matrix: Matrix, level: int, types: tuple[str, ...] | None = None
) -> dict[str, int]:
    """Subjects of one level per stage group (all types, or the given ones)."""
    out = dict.fromkeys(GROUP_ORDER, 0)
    for (lvl, typ, stage), n in matrix.items():
        if lvl != level or (types and typ not in types):
            continue
        out[group_of_stage(stage)] += max(n, 0)
    return out


def total_counts(matrix: Matrix, levels: list[int] | None = None) -> dict[str, int]:
    out = dict.fromkeys(GROUP_ORDER, 0)
    for (lvl, _typ, stage), n in matrix.items():
        if levels is not None and lvl not in levels:
            continue
        out[group_of_stage(stage)] += max(n, 0)
    return out


def pick_levels(all_levels: list[int], current: int | None, choice: str) -> list[int]:
    if not all_levels:
        return []
    if choice == "all" or current is None:
        return list(all_levels)
    if choice == "to_current":
        return [lvl for lvl in all_levels if lvl <= current]
    n = {"around3": 3, "around5": 5, "around10": 10}.get(choice, 5)
    lo = max(min(all_levels), current - n)
    return [lvl for lvl in all_levels if lo <= lvl <= current]


async def due_count(db: Db, account: str, now: datetime) -> int:
    return await db.current("assignments").count_documents(
        {
            "account": account,
            "hidden": False,
            "srs_stage": {"$gte": 1, "$lte": 8},
            "available_at": {"$lte": now},
        }
    )


async def current_level(db: Db, account: str) -> int | None:
    u = await db.current("user").find_one({"_id": account}, {"level": 1})
    return int(u["level"]) if u and u.get("level") is not None else None
