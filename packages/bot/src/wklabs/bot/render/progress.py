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

Json = dict[str, Any]
BAR_WIDTH = 10
GROUP_TITLE: dict[str, str] = {
    "locked": "Locked",
    "lesson": "Lessons",
    "apprentice": "Apprentice",
    "guru": "Guru",
    "master": "Master",
    "enlightened": "Enlightened",
    "burned": "Burned",
}


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


def counts_str(counts: dict[str, int]) -> str:
    return " ".join(f"{GROUP_EMOJI[g]}{counts.get(g, 0)}" for g in GROUP_ORDER)


def diff_str(before: dict[str, int], after: dict[str, int]) -> str:
    parts = [
        f"{GROUP_EMOJI[g]} {before.get(g, 0)}→{after.get(g, 0)}"
        for g in GROUP_ORDER
        if before.get(g, 0) != after.get(g, 0)
    ]
    return " · ".join(parts)


def level_line(
    level: int,
    after: dict[str, int],
    before: dict[str, int] | None,
    *,
    style: str,
    current: int | None = None,
) -> str:
    mark = "▶︎" if level == current else ""
    head = f"L{level}{mark}"
    parts: list[str] = []
    if style in ("emoji", "both"):
        parts.append(bar(after))
    if style in ("counts", "both"):
        parts.append(f"<code>{counts_str(after)}</code>")
    if before is not None:
        d = diff_str(before, after)
        if d:
            parts.append(d)
    return f"{head} " + " · ".join(parts)


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
    rows: list[str] = []
    ordered = sorted(levels, reverse=(sort == "desc"))
    for lvl in ordered:
        a = group_counts(after, lvl)
        b = group_counts(before, lvl) if before is not None else None
        if filter_ == "apprentice" and not a["apprentice"]:
            continue
        if filter_ == "changed" and (b is None or not diff_str(b, a)):
            continue
        rows.append(level_line(lvl, a, b, style=style, current=current))
    return rows


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
                per.append(f"L{lvl} {b}→{a}")
            elif a and g in ("apprentice", "lesson"):
                per.append(f"L{lvl} {a}")
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
            out.append(f"L{lvl} {d}")
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
    """The `/progress` message body (one message; the caller keeps it under the limit)."""
    rng = f"levels {min(levels)}–{max(levels)}" if levels else "no levels"
    arrow = "↓" if opts.get("sort") == "desc" else "↑"
    head = f"🗺 <b>{escape(label)}</b> · L{current or '?'} · {rng} {arrow}"
    if diff_title:
        head += f" · Δ {escape(diff_title)}"
    totals = total_counts(after, levels)
    tot_line = " ".join(f"{GROUP_EMOJI[g]} {totals[g]}" for g in GROUP_ORDER if totals[g])
    if due is not None:
        tot_line += f" · ⏳ due {due}"
    if opts.get("group") == "stage":
        body = stage_lines(after, before, levels)
    else:
        body = level_lines(
            after,
            before,
            levels,
            style=opts.get("style", "emoji"),
            sort=opts.get("sort", "asc"),
            filter_=opts.get("filter", "all"),
            current=current,
        )
    if not body:
        body = ["nothing to show with this filter"]
    foot = " · ".join(
        f"{k}: {option_label(k, opts[k])}" for k in ("levels", "filter", "style") if k in opts
    )
    return "\n".join([head, tot_line, "", *body, "", f"<i>{foot}</i>"])
