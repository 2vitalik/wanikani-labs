"""Per-notification settings: a registry the UI renders and the notifier reads (v2, T34 §2).

Layers: kind defaults ← account settings ← route settings. Every entry knows
which notification kinds it applies to and on which screen it lives
(`level` 1 = card, 2 = ⚙️ More…). A new setting is one entry here plus its use
in a renderer or sender; screens are generated from the registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .delivery import Route
from .progress import LEVELS_CHOICES, STYLE_CHOICES

BOOL, CHOICE, INT = "bool", "choice", "int"
Json = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Setting:
    key: str
    kind: str  # bool | choice | int
    default: Any  # a value, or {notification kind: value, "*": fallback}
    label: str
    help: str
    choices: tuple[tuple[str, str], ...] = ()  # choice: (value, shown as)
    presets: tuple[int, ...] = ()  # int: values the button cycles through
    range: tuple[int, int] = (0, 0)  # int: bounds for manual input
    kinds: tuple[str, ...] = ()  # empty = every notification kind
    level: int = 1  # 1 card · 2 More…
    unit: str = ""

    def applies(self, kind: str) -> bool:
        return not self.kinds or kind in self.kinds

    def default_for(self, kind: str) -> Any:
        if isinstance(self.default, dict):
            return self.default.get(kind, self.default.get("*"))
        return self.default

    def valid(self, value: Any) -> bool:
        if self.kind == BOOL:
            return isinstance(value, bool)
        if self.kind == INT:
            lo, hi = self.range
            return isinstance(value, int) and not isinstance(value, bool) and lo <= value <= hi
        return any(value == v for v, _ in self.choices)

    def shown(self, value: Any) -> str:
        if self.kind == BOOL:
            return "on" if value else "off"
        if self.kind == INT:
            return f"{value} {self.unit}".strip()
        return next((label for v, label in self.choices if v == value), str(value))

    def display(self, value: Any) -> str:
        return f"{self.label}: {self.shown(value)}"

    def next_value(self, current: Any) -> Any:
        if self.kind == BOOL:
            return not bool(current)
        if self.kind == INT:
            later = [p for p in self.presets if isinstance(current, int) and p > current]
            return later[0] if later else self.presets[0]
        values = [v for v, _ in self.choices]
        try:
            return values[(values.index(current) + 1) % len(values)]
        except ValueError:
            return values[0]


SILENT = Setting("silent", BOOL, False, "🔕 Silent", "silent — no notification sound")
ITEMS = Setting(
    "items",
    CHOICE,
    {"live": "all", "session": "wrong"},
    "📄 Items",
    "items — all / wrong only / counts only",
    choices=(("all", "all"), ("wrong", "wrong only"), ("none", "counts only")),
    kinds=("live", "session"),
)
SORT = Setting(
    "sort",
    CHOICE,
    "stage_asc",
    "↕️ Sort",
    "sort — item lists by SRS stage (↑ low first), misses or time",
    choices=(
        ("stage_asc", "stage ↑"),
        ("stage_desc", "stage ↓"),
        ("misses", "misses"),
        ("time", "time"),
    ),
    kinds=("live", "session"),
    level=2,
)
GROUP = Setting(
    "group",
    BOOL,
    True,
    "🗂 Group",
    "group — same SRS moves under one header",
    kinds=("live", "session"),
    level=2,
)
GAP = Setting(
    "gap",
    INT,
    15,
    "⏱ Gap",
    "gap — minutes of silence that end a session",
    presets=(5, 10, 15, 20, 30, 45, 60),
    range=(1, 240),
    kinds=("session",),
    unit="min",
)
LIVE = Setting(
    "live",
    BOOL,
    True,
    "📡 Live",
    "live — one message updated while you study, final summary when it ends",
    kinds=("session",),
)
MIN_ITEMS = Setting(
    "min_items",
    INT,
    3,
    "🔢 Min items",
    "min items — smaller sessions get no summary",
    presets=(1, 2, 3, 5, 10),
    range=(1, 100),
    kinds=("session",),
    level=2,
)
MOVES = Setting(
    "moves", BOOL, True, "📊 Moves", "moves — SRS ups/downs line", kinds=("session",), level=2
)
WINS = Setting(
    "wins", BOOL, True, "🏆 Wins", "wins — burned, passed, level-ups", kinds=("session",), level=2
)
LESSONS = Setting(
    "lessons", BOOL, True, "📖 Lessons", "lessons — items you started", kinds=("session",), level=2
)
CHANGES = Setting(
    "changes",
    BOOL,
    True,
    "🗺 Changes",
    "changes — per-level stage counts before → after",
    kinds=("session",),
    level=2,
)
MAP = Setting(
    "map", BOOL, False, "🗺 Map", "map — full level map at the end", kinds=("session",), level=2
)
MAP_LEVELS = Setting(
    "map_levels",
    CHOICE,
    "around5",
    "📐 Levels",
    "levels — which levels the map/changes show",
    choices=LEVELS_CHOICES,
    kinds=("session",),
    level=2,
)
MAP_STYLE = Setting(
    "map_style",
    CHOICE,
    "emoji",
    "🎨 Style",
    "style — emoji bars, counts, or both",
    choices=STYLE_CHOICES,
    kinds=("session",),
    level=2,
)

SETTINGS: tuple[Setting, ...] = (
    SILENT,
    ITEMS,
    SORT,
    GROUP,
    GAP,
    LIVE,
    MIN_ITEMS,
    MOVES,
    WINS,
    LESSONS,
    CHANGES,
    MAP,
    MAP_LEVELS,
    MAP_STYLE,
)
BY_KEY = {s.key: s for s in SETTINGS}
VIEW_KEYS: tuple[str, ...] = ("items", "sort", "group")  # buttons under a session message


def for_kind(kind: str, level: int | None = None) -> list[Setting]:
    return [s for s in SETTINGS if s.applies(kind) and (level is None or s.level == level)]


def effective(route: Route, account_settings: Json | None = None) -> Json:
    """Kind defaults ← account layer ← route layer, only keys that apply to the kind."""
    out: Json = {s.key: s.default_for(route.kind) for s in for_kind(route.kind)}
    for layer in (account_settings or {}, route.settings):
        for key, value in layer.items():
            if key in out and BY_KEY[key].valid(value):
                out[key] = value
    return out


def help_line(kind: str, level: int | None = 1) -> str:
    return " · ".join(s.help for s in for_kind(kind, level))
