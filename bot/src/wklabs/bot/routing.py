"""Forum topics and event-kind -> topic routing (change here, not in the schema)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Json = dict[str, Any]

# Telegram forum icon colours (the only values the API accepts)
BLUE, YELLOW, PURPLE, GREEN, PINK, RED = 7322096, 16766590, 13338331, 9367192, 16749490, 16478047


@dataclass(frozen=True, slots=True)
class TopicDef:
    key: str  # stable id stored in Mongo: "main.reviews", "subjects", "system"
    title: str
    icon_color: int


def topic_defs(accounts: list[str]) -> list[TopicDef]:
    out: list[TopicDef] = []
    for acc in accounts:
        out.append(TopicDef(f"{acc}.reviews", f"📝 {acc} · reviews", BLUE))
        out.append(TopicDef(f"{acc}.milestones", f"🏆 {acc} · milestones", YELLOW))
    out.append(TopicDef("subjects", "📚 subjects", PURPLE))
    out.append(TopicDef("system", "🛠 system", RED))
    return out


_KIND_GROUP: dict[str, str | None] = {
    "reviewed": "reviews",
    "srs_up": "reviews",
    "srs_down": "reviews",
    "unlocked": "reviews",
    "started": "reviews",
    "passed": "milestones",
    "burned": "milestones",
    "resurrected": "milestones",
    "level_started": "milestones",
    "level_passed": "milestones",
    "level_completed": "milestones",
    "level_abandoned": "milestones",
    "user_level": "milestones",
    "reset": "milestones",
    "subject_new": "subjects",
    "subject_updated": "subjects",
    "subject_hidden": "subjects",
    # not notified (state only):
    "hidden": None,
    "user_updated": None,
    "study_material": None,
    "resource_new": None,
    "resource_updated": None,
}


def topic_for(event: Json) -> str | None:
    group = _KIND_GROUP.get(str(event.get("kind")))
    if group is None:
        return None
    if group == "subjects":
        return "subjects"
    return f"{event.get('account')}.{group}"
