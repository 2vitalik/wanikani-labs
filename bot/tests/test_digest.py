from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from bson import ObjectId

from wklabs.bot.digest import render_topic
from wklabs.bot.routing import topic_defs, topic_for

TZ = ZoneInfo("Europe/Kyiv")
AT = datetime(2026, 8, 23, 12, 5, tzinfo=UTC)


def subj(sid, typ, chars, meaning, level=5):
    return {
        "_id": sid,
        "type": typ,
        "level": level,
        "characters": chars,
        "slug": chars,
        "item": {
            "data": {
                "meanings": [{"meaning": meaning, "primary": True}],
                "document_url": f"https://www.wanikani.com/{typ}/{chars}",
            }
        },
    }


SUBJECTS = {
    1: subj(1, "kanji", "火", "Fire"),
    2: subj(2, "vocabulary", "水曜日", "Wednesday"),
    3: subj(3, "radical", "一", "Ground", 1),
}


def ev(kind, sid, **meta):
    return {
        "_id": ObjectId(),
        "kind": kind,
        "at": AT,
        "account": "main",
        "subject_id": sid,
        "subject_type": SUBJECTS[sid]["type"] if sid in SUBJECTS else None,
        "meta": meta,
    }


def test_routing():
    assert topic_for(ev("reviewed", 1)) == "main.reviews"
    assert topic_for(ev("burned", 1)) == "main.milestones"
    assert topic_for(ev("subject_updated", 1)) == "subjects"
    assert topic_for(ev("hidden", 1)) is None
    keys = [t.key for t in topic_defs(["main", "light"])]
    assert keys == [
        "main.reviews",
        "main.milestones",
        "light.reviews",
        "light.milestones",
        "subjects",
        "system",
    ]


def test_reviews_digest():
    events = [
        ev("reviewed", 1, count=1, meaning_wrong=0, reading_wrong=0, correct=True),
        ev("srs_up", 1, from_stage=4, to_stage=5),
        ev("reviewed", 2, count=1, meaning_wrong=1, reading_wrong=0, correct=False),
        ev("srs_down", 2, from_stage=6, to_stage=4),
        ev("unlocked", 3),
    ]
    msgs = render_topic("main.reviews", events, SUBJECTS, TZ)
    assert len(msgs) == 1
    text = msgs[0]
    assert "<b>main</b> · 15:05" in text  # Kyiv = UTC+3 in summer
    assert "2 reviews: ✅ 1 · ❌ 1 · ⬆️ 1 · ⬇️ 1" in text
    assert "🔓 1 unlocked" in text
    lines = text.split("\n")
    # wrong answers listed first
    assert (
        lines[1].startswith("❌")
        and "水曜日" in lines[1]
        and "Guru II → 🩷Apprentice IV" in lines[1]
    )
    assert "(m1 r0)" in lines[1]
    assert lines[2].startswith("✅") and "Apprentice IV → 💜Guru I" in lines[2]
    assert 'href="https://www.wanikani.com/kanji/火"' in text
    assert "🔓 unlocked: " in lines[3] and "一" in lines[3]


def test_milestones_and_subjects():
    msgs = render_topic(
        "main.milestones",
        [ev("burned", 1), ev("passed", 2), ev("user_level", None, from_level=39, to_level=40)],
        SUBJECTS,
        TZ,
    )
    t = msgs[0]
    assert "🎉 <b>Level 40!</b>" in t and "🔥 burned (1): " in t and "💜 passed (Guru) (1)" in t
    e = ev("subject_updated", 1, changed=["meaning_mnemonic", "context_sentences"])
    e["account"] = None
    t2 = render_topic("subjects", [e], SUBJECTS, TZ)[0]
    assert "✏️" in t2 and "meaning_mnemonic, context_sentences" in t2 and "updated 1" in t2


def test_long_digest_splits_and_truncates():
    many = {i: subj(i, "vocabulary", f"語{i}", "Word " * 10) for i in range(1, 200)}
    events = [
        ev("reviewed", i, count=1, meaning_wrong=0, reading_wrong=0, correct=True)
        for i in range(1, 200)
    ]
    for e in events:
        e["subject_type"] = "vocabulary"
    msgs = render_topic("main.reviews", events, many, TZ)
    assert all(len(m) <= 4096 for m in msgs)
    assert "… +139 more" in msgs[-1]  # MAX_LINES = 60
    assert all(m.startswith("📝 <b>main</b>") for m in msgs)
