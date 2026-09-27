"""Level map à la wkstats: one line per level (emoji bar / counts), or per stage group, with
before → after diffs (T33 §3.3). Pure: matrices in, HTML lines out."""

from __future__ import annotations

from html import escape
from typing import Any

from wklabs.lib.progress import (
    GROUP_EMOJI,
    GROUP_ORDER,
    Matrix,
    group_counts,
    option_label,
    total_counts,
)
from wklabs.lib.subjects import level_tag

from .common import MAX_LEN, tg_len

Json = dict[str, Any]
BAR_WIDTH = 10
BOTH_BAR_WIDTH = 6  # `both`: a shorter bar leaves room for the numbers on a phone
CURRENT_MARK = "◂"  # plain text glyph (no emoji variant), trails the current level
GROUP_TITLE: dict[str, str] = {
    "locked": "Locked",
    "lesson": "Lessons",
    "apprentice": "Apprentice",
    "guru": "Guru",
    "master": "Master",
    "enlightened": "Enlightened",
    "burned": "Burned",
}
Widths = dict[str, int]


def bar(counts: dict[str, int], width: int = BAR_WIDTH) -> str:
    """Proportional emoji bar in stage order (largest remainder, exactly `width` cells)."""
    total = sum(max(n, 0) for n in counts.values())
    if total <= 0:
        return "▫️" * width
    raw = {g: width * max(counts.get(g, 0), 0) / total for g in GROUP_ORDER}
    cells = {g: int(v) for g, v in raw.items()}
    for g in sorted(GROUP_ORDER, key=lambda g: raw[g] - cells[g], reverse=True):
        if sum(cells.values()) >= width:
            break
        cells[g] += 1
    return "".join(GROUP_EMOJI[g] * cells[g] for g in GROUP_ORDER)


def visible_groups(after: Matrix, levels: list[int]) -> list[str]:
    """Stage groups that exist somewhere in the shown levels — the columns of a counts table."""
    totals = total_counts(after, levels)
    return [g for g in GROUP_ORDER if totals.get(g)]


def column_widths(after: Matrix, levels: list[int], cols: list[str]) -> Widths:
    w = dict.fromkeys(cols, 1)
    for lvl in levels:
        c = group_counts(after, lvl)
        for g in cols:
            w[g] = max(w[g], len(str(c.get(g, 0))))
    return w


def counts_str(counts: dict[str, int], cols: list[str], widths: Widths) -> str:
    """`🩷 12 💜  3 🔥 40` — numbers right-aligned per column, for <code>."""
    return " ".join(f"{GROUP_EMOJI[g]}{counts.get(g, 0):>{widths[g]}}" for g in cols)


def numbers_str(counts: dict[str, int], cols: list[str], widths: Widths) -> str:
    """`12  3 40` — the same columns without emoji (the totals line is the legend)."""
    return " ".join(f"{counts.get(g, 0):>{widths[g]}}" for g in cols)


def diff_str(before: dict[str, int], after: dict[str, int]) -> str:
    parts = [
        f"{GROUP_EMOJI[g]} {before.get(g, 0)}→{after.get(g, 0)}"
        for g in GROUP_ORDER
        if before.get(g, 0) != after.get(g, 0)
    ]
    return " · ".join(parts)


def level_head(level: int, current: int | None) -> str:
    """`L07`; the current level in bold — same width, nothing shifts (T38 §2)."""
    tag = level_tag(level)
    return f"<b>{tag}</b>" if level == current else tag


def level_line(
    level: int,
    after: dict[str, int],
    before: dict[str, int] | None,
    *,
    style: str,
    current: int | None = None,
    cols: list[str],
    widths: Widths,
) -> list[str]:
    """One level, one line: bar (`emoji`), counts table (`counts`) or short bar │ numbers
    (`both`); then the diff, then the current-level mark."""
    head = level_head(level, current)
    if style == "counts":
        body = f"<code>{counts_str(after, cols, widths)}</code>"
    elif style == "both":
        numbers = numbers_str(after, cols, widths)
        body = f"{bar(after, BOTH_BAR_WIDTH)} <code>│ {numbers}</code>"
    else:
        body = bar(after)
    line = f"{head} {body}"
    if before is not None:
        d = diff_str(before, after)
        if d:
            line += f" · {d}"
    if level == current:
        line += f" {CURRENT_MARK}"
    return [line]


def level_rows(
    after: Matrix,
    before: Matrix | None,
    levels: list[int],
    *,
    style: str = "emoji",
    sort: str = "asc",
    filter_: str = "all",
    current: int | None = None,
) -> list[list[str]]:
    """One row (1–2 lines) per level, in display order."""
    rows: list[list[str]] = []
    ordered = sorted(levels, reverse=(sort == "desc"))
    cols = visible_groups(after, levels)
    widths = column_widths(after, levels, cols)
    for lvl in ordered:
        a = group_counts(after, lvl)
        b = group_counts(before, lvl) if before is not None else None
        if filter_ == "apprentice" and not a["apprentice"]:
            continue
        if filter_ == "changed" and (b is None or not diff_str(b, a)):
            continue
        rows.append(level_line(lvl, a, b, style=style, current=current, cols=cols, widths=widths))
    return rows


def level_lines(
    after: Matrix,
    before: Matrix | None,
    levels: list[int],
    *,
    style: str = "emoji",
    sort: str = "asc",
    filter_: str = "all",
    current: int | None = None,
) -> list[str]:
    return [
        ln
        for row in level_rows(
            after, before, levels, style=style, sort=sort, filter_=filter_, current=current
        )
        for ln in row
    ]


def stage_lines(after: Matrix, before: Matrix | None, levels: list[int]) -> list[str]:
    """One line per stage group: total (Δ) and the levels where it changed / lives."""
    rows: list[str] = []
    ta = total_counts(after, levels)
    tb = total_counts(before, levels) if before is not None else None
    for g in GROUP_ORDER:
        n = ta.get(g, 0)
        if not n and not (tb and tb.get(g)):
            continue
        head = f"{GROUP_EMOJI[g]} <b>{GROUP_TITLE[g]}</b> {n}"
        if tb is not None and tb.get(g, 0) != n:
            delta = n - tb.get(g, 0)
            head += f" ({'+' if delta > 0 else ''}{delta})"
        per: list[str] = []
        for lvl in levels:
            a = group_counts(after, lvl).get(g, 0)
            b = group_counts(before, lvl).get(g, 0) if before is not None else a
            if a != b:
                per.append(f"{level_tag(lvl)} {b}→{a}")
            elif a and g in ("apprentice", "lesson"):
                per.append(f"{level_tag(lvl)} {a}")
        rows.append(head + (": " + " · ".join(per[:12]) if per else ""))
    return rows


def changed_lines(after: Matrix, before: Matrix, levels: list[int] | None = None) -> list[str]:
    """`L37 🩷 5→3 · 💜 12→14` for every level with a change (the session "what changed")."""
    lvls = (
        levels
        if levels is not None
        else sorted({lvl for (lvl, _t, _s) in after} | {lvl for (lvl, _t, _s) in before})
    )
    out: list[str] = []
    for lvl in lvls:
        d = diff_str(group_counts(before, lvl), group_counts(after, lvl))
        if d:
            out.append(f"{level_tag(lvl)} {d}")
    return out


def fit_rows(rows: list[list[str]], budget: int, *, drop_start: bool) -> list[str]:
    """Flatten rows into ≤ `budget` Telegram units, dropping whole levels from the far end."""
    kept = list(rows)
    dropped = 0
    while len(kept) > 1 and sum(tg_len(ln) + 1 for row in kept for ln in row) > budget:
        kept.pop(0) if drop_start else kept.pop()
        dropped += 1
    out = [ln for row in kept for ln in row]
    if dropped:
        note = f"… +{dropped} levels don't fit — narrow the range or pick another style"
        out.insert(0, note) if drop_start else out.append(note)
    return out


def render_map(
    label: str,
    current: int | None,
    levels: list[int],
    after: Matrix,
    before: Matrix | None,
    opts: dict[str, str],
    *,
    due: int | None = None,
    diff_title: str = "",
) -> str:
    """The `/progress` message body — one message, trimmed to Telegram's limit."""
    rng = f"levels {min(levels)}–{max(levels)}" if levels else "no levels"
    desc = opts.get("sort") == "desc"
    arrow = "↓" if desc else "↑"
    head = f"🗺 <b>{escape(label)}</b> · {level_tag(current)} · {rng} {arrow}"
    if diff_title:
        head += f" · Δ {escape(diff_title)}"
    totals = total_counts(after, levels)
    tot_line = " ".join(f"{GROUP_EMOJI[g]} {totals[g]}" for g in GROUP_ORDER if totals[g])
    if due is not None:
        tot_line += f" · ⏳ due {due}"
    foot = " · ".join(f"{k}: {option_label(k, opts[k])}" for k in ("filter", "style") if k in opts)
    frame = [head, tot_line, "", "", f"<i>{foot}</i>"]
    budget = MAX_LEN - sum(tg_len(x) + 1 for x in frame)
    if opts.get("group") == "stage":
        body = stage_lines(after, before, levels)
    else:
        rows = level_rows(
            after,
            before,
            levels,
            style=opts.get("style", "emoji"),
            sort=opts.get("sort", "asc"),
            filter_=opts.get("filter", "all"),
            current=current,
        )
        # the current level sits at the end when ascending: drop far (low) levels first
        body = fit_rows(rows, budget, drop_start=not desc)
    if not body:
        body = ["nothing to show with this filter"]
    return "\n".join([head, tot_line, "", *body, "", f"<i>{foot}</i>"])
