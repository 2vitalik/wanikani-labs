"""Event kind -> delivery category (change here, not in the schema).

Categories are delivery channels (`lib.delivery`): account-scoped `reviews` /
`milestones`, global `subjects` / `system`. `None` = state only, not notified.
"""

from __future__ import annotations

from typing import Any

from wklabs.lib.delivery import GLOBAL_CATEGORIES

Json = dict[str, Any]

_KIND_CATEGORY: dict[str, str | None] = {
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


def category_for(kind: str) -> str | None:
    return _KIND_CATEGORY.get(kind)


def target_for(event: Json) -> tuple[str | None, str] | None:
    """`(account, category)` a stored event is delivered as; None = silent."""
    category = category_for(str(event.get("kind")))
    if category is None:
        return None
    if category in GLOBAL_CATEGORIES:
        return (None, category)
    return (event.get("account"), category)
