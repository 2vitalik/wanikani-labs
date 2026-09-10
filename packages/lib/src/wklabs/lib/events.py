"""Derive events from consecutive versions of a resource (prev -> cur).

Pure functions: the same code runs live (sync) and in `rebuild-events`
(replaying `history`), so the event stream is always reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .timeutil import parse_ts

Json = dict[str, Any]

# kinds, grouped for routing/digests
ASSIGNMENT_KINDS = (
    "unlocked",
    "started",
    "srs_up",
    "srs_down",
    "passed",
    "burned",
    "resurrected",
    "hidden",
)
REVIEW_KINDS = ("reviewed",)
LEVEL_KINDS = ("level_started", "level_passed", "level_completed", "level_abandoned")
USER_KINDS = ("user_level", "user_updated")
SUBJECT_KINDS = ("subject_new", "subject_updated", "subject_hidden")
OTHER_KINDS = ("reset", "study_material", "resource_new", "resource_updated")

SUBJECT_DIFF_KEYS = (
    "level",
    "slug",
    "characters",
    "meanings",
    "auxiliary_meanings",
    "readings",
    "meaning_mnemonic",
    "meaning_hint",
    "reading_mnemonic",
    "reading_hint",
    "component_subject_ids",
    "amalgamation_subject_ids",
    "visually_similar_subject_ids",
    "context_sentences",
    "parts_of_speech",
    "pronunciation_audios",
    "lesson_position",
    "hidden_at",
    "document_url",
    "character_images",
)


@dataclass(slots=True)
class Event:
    kind: str
    at: datetime
    resource: str
    resource_id: int | str
    account: str | None
    subject_id: int | None = None
    subject_type: str | None = None
    prev: Json = field(default_factory=dict)
    cur: Json = field(default_factory=dict)
    meta: Json = field(default_factory=dict)

    def to_doc(self) -> Json:
        return {
            "kind": self.kind,
            "at": self.at,
            "resource": self.resource,
            "resource_id": self.resource_id,
            "account": self.account,
            "subject_id": self.subject_id,
            "subject_type": self.subject_type,
            "prev": self.prev,
            "cur": self.cur,
            "meta": self.meta,
        }


def _data(item: Json | None) -> Json:
    return (item or {}).get("data") or {}


def _set_now(prev: Json, cur: Json, key: str) -> bool:
    return not prev.get(key) and bool(cur.get(key))


def derive_events(
    resource: str,
    account: str | None,
    prev_item: Json | None,
    cur_item: Json,
    *,
    first_seen_counts: bool,
) -> list[Event]:
    """Events for the transition prev -> cur.

    `first_seen_counts`: when `prev_item is None` — True for a live incremental
    run (a new assignment really is an unlock); False for baseline/import
    (first observation, nothing "happened").
    """
    if prev_item is None and not first_seen_counts:
        return []
    at = parse_ts(cur_item.get("data_updated_at")) or parse_ts(_data(cur_item).get("created_at"))
    assert at is not None, "item without data_updated_at"
    rid: int | str = cur_item.get("id", account or "")
    p, c = _data(prev_item), _data(cur_item)

    def ev(kind: str, **meta: Any) -> Event:
        return Event(
            kind=kind,
            at=at,
            resource=resource,
            resource_id=rid,
            account=account,
            subject_id=c.get("subject_id") if resource != "subjects" else int(rid),
            subject_type=c.get("subject_type")
            if resource != "subjects"
            else cur_item.get("object"),
            meta=meta,
        )

    out: list[Event] = []
    match resource:
        case "assignments":
            if _set_now(p, c, "unlocked_at"):
                out.append(ev("unlocked"))
            if _set_now(p, c, "started_at"):
                out.append(ev("started"))
            ps, cs = p.get("srs_stage"), c.get("srs_stage")
            if ps is not None and cs is not None and ps != cs:
                out.append(ev("srs_up" if cs > ps else "srs_down", from_stage=ps, to_stage=cs))
            if _set_now(p, c, "passed_at"):
                out.append(ev("passed", stage=cs))
            if _set_now(p, c, "burned_at"):
                out.append(ev("burned"))
            if _set_now(p, c, "resurrected_at"):
                out.append(ev("resurrected", stage=cs))
            if not p.get("hidden") and c.get("hidden"):
                out.append(ev("hidden"))
        case "review_statistics":
            d_mc = (c.get("meaning_correct") or 0) - (p.get("meaning_correct") or 0)
            d_mi = (c.get("meaning_incorrect") or 0) - (p.get("meaning_incorrect") or 0)
            d_rc = (c.get("reading_correct") or 0) - (p.get("reading_correct") or 0)
            d_ri = (c.get("reading_incorrect") or 0) - (p.get("reading_incorrect") or 0)
            if any(x > 0 for x in (d_mc, d_mi, d_rc, d_ri)):
                # one review per item ends with one correct meaning answer
                count = max(d_mc, d_rc, 1)
                out.append(
                    ev(
                        "reviewed",
                        count=count,
                        meaning_wrong=d_mi,
                        reading_wrong=d_ri,
                        correct=(d_mi == 0 and d_ri == 0),
                        percentage=c.get("percentage_correct"),
                    )
                )
        case "level_progressions":
            lvl = c.get("level")
            for key, kind in (
                ("started_at", "level_started"),
                ("passed_at", "level_passed"),
                ("completed_at", "level_completed"),
                ("abandoned_at", "level_abandoned"),
            ):
                if _set_now(p, c, key):
                    out.append(ev(kind, level=lvl))
            if not out and prev_item is None and c.get("unlocked_at"):
                out.append(ev("level_started", level=lvl, unlocked_only=True))
        case "user":
            if prev_item is not None and p.get("level") != c.get("level"):
                out.append(ev("user_level", from_level=p.get("level"), to_level=c.get("level")))
            changed = [
                k
                for k in (
                    "subscription",
                    "preferences",
                    "current_vacation_started_at",
                    "username",
                    "profile_url",
                )
                if prev_item is not None and p.get(k) != c.get(k)
            ]
            if changed:
                out.append(ev("user_updated", changed=changed))
        case "subjects":
            if prev_item is None:
                out.append(ev("subject_new", level=c.get("level")))
            else:
                changed = [k for k in SUBJECT_DIFF_KEYS if p.get(k) != c.get(k)]
                if _set_now(p, c, "hidden_at"):
                    out.append(ev("subject_hidden", level=c.get("level")))
                    changed = [k for k in changed if k != "hidden_at"]
                if changed:
                    out.append(ev("subject_updated", changed=changed, level=c.get("level")))
        case "resets":
            if prev_item is None:
                out.append(
                    ev(
                        "reset",
                        original_level=c.get("original_level"),
                        target_level=c.get("target_level"),
                    )
                )
        case "study_materials":
            out.append(ev("study_material", new=prev_item is None))
        case "summary":
            pass  # state only
        case _:
            out.append(ev("resource_new" if prev_item is None else "resource_updated"))
    return out
