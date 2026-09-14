"""Event kind -> notification kind for instant delivery (change here, not in the schema).

Kinds are delivery channels (`lib.delivery.KINDS`): account-scoped `live` /
`milestones`, global `subjects` / `system`. `None` = state only, not notified.
Sessions consume every account event of their window on their own (T32 §5).
"""

from __future__ import annotations

from typing import Any

from wklabs.lib.delivery import GLOBAL_KINDS

Json = dict[str, Any]

_EVENT_KIND: dict[str, str | None] = {
    "reviewed": "live",
    "srs_up": "live",
    "srs_down": "live",
    "unlocked": "live",
    "started": "live",
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


def kind_for(event_kind: str) -> str | None:
    return _EVENT_KIND.get(event_kind)


def target_for(event: Json) -> tuple[str | None, str] | None:
    """`(account, kind)` a stored event is delivered as; None = silent."""
    kind = kind_for(str(event.get("kind")))
    if kind is None:
        return None
    if kind in GLOBAL_KINDS:
        return (None, kind)
    return (event.get("account"), kind)
