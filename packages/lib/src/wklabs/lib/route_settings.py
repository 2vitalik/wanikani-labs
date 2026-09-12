"""Per-route delivery settings: a registry the UI renders and the notifier reads.

Layers (T07 §4): code defaults ← account settings ← route settings. A new
setting is one entry here plus its use in the renderer or sender; the route
screen draws a toggle (bool) or a cycling button (choice) for each entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .delivery import Route

BOOL, CHOICE = "bool", "choice"
Json = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Setting:
    key: str
    kind: str
    default: Any
    label: str
    help: str
    choices: tuple[tuple[str, str], ...] = ()  # (value, shown as)
    categories: tuple[str, ...] = ()  # empty = every category

    def applies(self, category: str) -> bool:
        return not self.categories or category in self.categories

    def valid(self, value: Any) -> bool:
        if self.kind == BOOL:
            return isinstance(value, bool)
        return any(value == v for v, _ in self.choices)

    def shown(self, value: Any) -> str:
        if self.kind == BOOL:
            return "on" if value else "off"
        return next((label for v, label in self.choices if v == value), str(value))

    def display(self, value: Any) -> str:
        return f"{self.label}: {self.shown(value)}"

    def next_value(self, current: Any) -> Any:
        if self.kind == BOOL:
            return not bool(current)
        values = [v for v, _ in self.choices]
        try:
            return values[(values.index(current) + 1) % len(values)]
        except ValueError:
            return values[0]


SILENT = Setting("silent", BOOL, False, "🔕 Silent", "silent — no notification sound")
ITEMS = Setting(
    "items",
    CHOICE,
    "all",
    "📄 Items",
    "items — all / wrong only / counts only",
    choices=(("all", "all"), ("wrong", "wrong only"), ("none", "counts only")),
    categories=("reviews",),
)
ROUTE_SETTINGS: tuple[Setting, ...] = (SILENT, ITEMS)
BY_KEY = {s.key: s for s in ROUTE_SETTINGS}


def for_category(category: str) -> list[Setting]:
    return [s for s in ROUTE_SETTINGS if s.applies(category)]


def effective(route: Route, account_settings: Json | None = None) -> Json:
    """Defaults ← account layer ← route layer, only keys that apply to the category."""
    out: Json = {s.key: s.default for s in for_category(route.category)}
    for layer in (account_settings or {}, route.settings):
        for key, value in layer.items():
            if key in out and BY_KEY[key].valid(value):
                out[key] = value
    return out


def help_line(category: str) -> str:
    return " · ".join(s.help for s in for_category(category))
