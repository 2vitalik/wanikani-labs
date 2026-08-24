"""Subject lookup + one-line rendering shared by bot digests and CLI."""

from __future__ import annotations

from typing import Any

from .db import Db

Json = dict[str, Any]

TYPE_EMOJI = {"radical": "🔵", "kanji": "🩷", "vocabulary": "🟣", "kana_vocabulary": "🟪"}
TYPE_SHORT = {"radical": "R", "kanji": "K", "vocabulary": "V", "kana_vocabulary": "KV"}


async def load_subjects(db: Db, ids: set[int]) -> dict[int, Json]:
    out: dict[int, Json] = {}
    if not ids:
        return out
    async for d in db.col("subjects").find({"_id": {"$in": sorted(ids)}}):
        out[int(d["_id"])] = d
    return out


def primary_meaning(subject: Json | None) -> str:
    if not subject:
        return ""
    data = (subject.get("item") or {}).get("data") or {}
    for m in data.get("meanings") or []:
        if m.get("primary"):
            return str(m.get("meaning", ""))
    ms = data.get("meanings") or []
    return str(ms[0]["meaning"]) if ms else ""


def primary_reading(subject: Json | None) -> str:
    if not subject:
        return ""
    data = (subject.get("item") or {}).get("data") or {}
    for r in data.get("readings") or []:
        if r.get("primary"):
            return str(r.get("reading", ""))
    return ""


def subject_label(
    subject: Json | None, subject_id: int | None = None, subject_type: str | None = None
) -> str:
    """`漢 (kanji L12) · Chinese` — characters (or slug), type, level, meaning."""
    if not subject:
        return f"#{subject_id} ({subject_type or '?'})"
    chars = subject.get("characters") or subject.get("slug") or f"#{subject.get('_id')}"
    typ = str(subject.get("type") or subject_type or "?")
    meaning = primary_meaning(subject)
    return f"{chars} · {meaning} ({TYPE_SHORT.get(typ, typ)}{subject.get('level', '?')})"


def subject_url(subject: Json | None) -> str | None:
    if not subject:
        return None
    return ((subject.get("item") or {}).get("data") or {}).get("document_url")
