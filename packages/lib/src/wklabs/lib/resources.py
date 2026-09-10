"""Registry of WaniKani resources we collect, and how each maps to Mongo.

`hoist(item)` returns typed top-level fields (BSON dates, ints) stored next to
the untouched raw `data` for indexing/queries. `subject_id(item)` links an item
to a subject for events/digests.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from .timeutil import parse_ts

Json = dict[str, Any]
Scope = Literal["global", "account"]


@dataclass(frozen=True, slots=True)
class Resource:
    name: str  # key; also `history.resource`
    endpoint: str
    scope: Scope
    singleton: bool = False  # `user`, `summary`: one object, no id
    params: dict[str, Any] = field(default_factory=dict)
    hoist: Callable[[Json], Json] = lambda item: {}
    subject_id: Callable[[Json], int | None] = lambda item: None


def _d(item: Json) -> Json:
    return item.get("data") or {}


def _sid(item: Json) -> int | None:
    v = _d(item).get("subject_id")
    return int(v) if v is not None else None


def _hoist_subject(item: Json) -> Json:
    d = _d(item)
    return {
        "type": item.get("object"),
        "level": d.get("level"),
        "slug": d.get("slug"),
        "characters": d.get("characters"),
        "hidden_at": parse_ts(d.get("hidden_at")),
        "lesson_position": d.get("lesson_position"),
        "srs_system_id": d.get("spaced_repetition_system_id"),
    }


def _hoist_assignment(item: Json) -> Json:
    d = _d(item)
    return {
        "subject_id": d.get("subject_id"),
        "subject_type": d.get("subject_type"),
        "srs_stage": d.get("srs_stage"),
        "unlocked_at": parse_ts(d.get("unlocked_at")),
        "started_at": parse_ts(d.get("started_at")),
        "passed_at": parse_ts(d.get("passed_at")),
        "burned_at": parse_ts(d.get("burned_at")),
        "available_at": parse_ts(d.get("available_at")),
        "resurrected_at": parse_ts(d.get("resurrected_at")),
        "hidden": bool(d.get("hidden", False)),
    }


def _hoist_review_stats(item: Json) -> Json:
    d = _d(item)
    keys = (
        "subject_id",
        "subject_type",
        "meaning_correct",
        "meaning_incorrect",
        "meaning_max_streak",
        "meaning_current_streak",
        "reading_correct",
        "reading_incorrect",
        "reading_max_streak",
        "reading_current_streak",
        "percentage_correct",
        "hidden",
    )
    return {k: d.get(k) for k in keys}


def _hoist_level_progression(item: Json) -> Json:
    d = _d(item)
    return {
        "level": d.get("level"),
        "unlocked_at": parse_ts(d.get("unlocked_at")),
        "started_at": parse_ts(d.get("started_at")),
        "passed_at": parse_ts(d.get("passed_at")),
        "completed_at": parse_ts(d.get("completed_at")),
        "abandoned_at": parse_ts(d.get("abandoned_at")),
    }


def _hoist_study_material(item: Json) -> Json:
    d = _d(item)
    return {
        "subject_id": d.get("subject_id"),
        "subject_type": d.get("subject_type"),
        "hidden": bool(d.get("hidden", False)),
    }


def _hoist_reset(item: Json) -> Json:
    d = _d(item)
    return {
        "original_level": d.get("original_level"),
        "target_level": d.get("target_level"),
        "confirmed_at": parse_ts(d.get("confirmed_at")),
    }


def _hoist_named(item: Json) -> Json:
    return {"name": _d(item).get("name")}


def _hoist_user(item: Json) -> Json:
    d = _d(item)
    sub = d.get("subscription") or {}
    return {
        "username": d.get("username"),
        "level": d.get("level"),
        "max_level": sub.get("max_level_granted"),
        "subscription_active": sub.get("active"),
        "subscription_type": sub.get("type"),
        "started_at": parse_ts(d.get("started_at")),
        "vacation_started_at": parse_ts(d.get("current_vacation_started_at")),
    }


def _hoist_summary(item: Json) -> Json:
    d = _d(item)
    reviews = d.get("reviews") or []
    lessons = d.get("lessons") or []
    return {
        "next_reviews_at": parse_ts(d.get("next_reviews_at")),
        "reviews_now": len(reviews[0].get("subject_ids") or []) if reviews else 0,
        "reviews_24h": sum(len(r.get("subject_ids") or []) for r in reviews),
        "lessons_now": sum(len(le.get("subject_ids") or []) for le in lessons),
    }


RESOURCES: dict[str, Resource] = {
    r.name: r
    for r in (
        Resource(
            "subjects",
            "subjects",
            "global",
            hoist=_hoist_subject,
            subject_id=lambda item: int(item["id"]),
        ),
        Resource("srs_systems", "spaced_repetition_systems", "global", hoist=_hoist_named),
        Resource("voice_actors", "voice_actors", "global", hoist=_hoist_named),
        Resource("user", "user", "account", singleton=True, hoist=_hoist_user),
        Resource("summary", "summary", "account", singleton=True, hoist=_hoist_summary),
        Resource(
            "level_progressions", "level_progressions", "account", hoist=_hoist_level_progression
        ),
        Resource("assignments", "assignments", "account", hoist=_hoist_assignment, subject_id=_sid),
        Resource(
            "review_statistics",
            "review_statistics",
            "account",
            hoist=_hoist_review_stats,
            subject_id=_sid,
        ),
        Resource(
            "study_materials",
            "study_materials",
            "account",
            hoist=_hoist_study_material,
            subject_id=_sid,
        ),
        Resource("resets", "resets", "account", hoist=_hoist_reset),
    )
}

# Poll groups (order matters: user/summary first — cheap, show activity; subjects
# before assignments so digests can resolve characters on a fresh DB).
GLOBAL_RESOURCES: tuple[str, ...] = ("subjects", "srs_systems", "voice_actors")
ACCOUNT_RESOURCES: tuple[str, ...] = (
    "user",
    "summary",
    "level_progressions",
    "assignments",
    "review_statistics",
    "study_materials",
    "resets",
)

SRS_STAGES: dict[int, str] = {
    0: "Locked",
    1: "Apprentice I",
    2: "Apprentice II",
    3: "Apprentice III",
    4: "Apprentice IV",
    5: "Guru I",
    6: "Guru II",
    7: "Master",
    8: "Enlightened",
    9: "Burned",
}
