"""Window statistics and the progress matrix with reverse replay."""

from datetime import UTC, datetime, timedelta

from wklabs.lib.progress import (
    LOCKED,
    group_counts,
    levels_of,
    next_option,
    normalize_options,
    pick_levels,
    reverse_apply,
    stage_matrix,
    subject_index,
    total_counts,
)
from wklabs.lib.stats import window_stats

T0 = datetime(2026, 9, 13, 17, 52, tzinfo=UTC)
SUBJECTS = {
    1: {"_id": 1, "level": 12, "type": "kanji"},
    2: {"_id": 2, "level": 5, "type": "vocabulary"},
    3: {"_id": 3, "level": 1, "type": "radical"},
    4: {"_id": 4, "level": 12, "type": "kana_vocabulary"},
}


def ev(kind, sid, minutes=0, **meta):
    return {
        "kind": kind,
        "at": T0 + timedelta(minutes=minutes),
        "account": "a",
        "subject_id": sid,
        "subject_type": SUBJECTS[sid]["type"] if sid in SUBJECTS else None,
        "meta": meta,
    }


def test_window_stats():
    events = [
        ev("reviewed", 1, 0, count=1, correct=True, meaning_wrong=0, reading_wrong=0),
        ev("srs_up", 1, 0, from_stage=4, to_stage=5),
        ev("passed", 1, 0),
        ev("reviewed", 2, 3, count=1, correct=False, meaning_wrong=1, reading_wrong=2),
        ev("srs_down", 2, 3, from_stage=6, to_stage=4),
        ev("reviewed", 4, 9, count=2, correct=True, meaning_wrong=0, reading_wrong=0),
        ev("srs_up", 4, 9, from_stage=8, to_stage=9),
        ev("burned", 4, 9),
        ev("started", 3, 10),
        ev("srs_up", 3, 10, from_stage=0, to_stage=1),
        ev("unlocked", 3, 10),
        ev("user_level", None, 10, from_level=39, to_level=40),
        ev("level_passed", None, 10, level=39),
    ]
    st = window_stats(events, SUBJECTS)
    assert (st.n_items, st.n_reviews, st.ok, st.bad) == (3, 4, 2, 1)
    assert st.meaning_wrong == 1 and st.reading_wrong == 2
    # answers: kanji 1 → 2, vocab 1 → 2 (+3 wrong), kana vocab 2 → 2 (no reading) = 6 + 3
    assert st.answers == 9 and st.answers_wrong == 3
    assert round(st.acc_items or 0, 3) == 0.667 and round(st.acc_answers or 0, 3) == 0.667
    assert st.up == 3 and st.down == 1 and st.to_group == {"guru": 1, "burned": 1}
    assert st.by_type == {"kanji": (1, 0), "vocabulary": (1, 1), "kana_vocabulary": (1, 0)}
    assert st.by_level == {5: (1, 1), 12: (2, 0)}
    assert st.lessons == [3] and st.unlocked == [3] and st.passed == [1] and st.burned == [4]
    assert st.level_ups == [(39, 40)] and st.level_events == [("level_passed", 39)]
    assert st.duration == timedelta(minutes=10) and st.longest_pause == timedelta(minutes=6)
    assert st.pace == 0.3 and st.kind == "mixed" and st.n_instants == 4
    wrong = st.wrong_items
    assert [it.subject_id for it in wrong] == [2] and wrong[0].wrong and wrong[0].to_stage == 4
    doc = st.to_doc()
    assert (
        doc["n_items"] == 3 and doc["to_group"] == {"guru": 1, "burned": 1} and doc["lessons"] == 1
    )
    assert window_stats([]).kind == "none" and window_stats([]).acc_items is None
    only = window_stats([ev("started", 3, 0)], SUBJECTS)
    assert only.kind == "lessons" and only.pace is None


async def test_matrix_and_reverse_apply(db):
    await db.col("subjects").insert_many(
        [
            {"_id": 1, "level": 1, "type": "kanji", "hidden_at": None},
            {"_id": 2, "level": 1, "type": "kanji", "hidden_at": None},
            {"_id": 3, "level": 2, "type": "vocabulary", "hidden_at": None},
            {"_id": 4, "level": 2, "type": "vocabulary", "hidden_at": None},
            {"_id": 5, "level": 2, "type": "vocabulary", "hidden_at": T0},  # hidden: ignored
        ]
    )
    await db.col("assignments").insert_many(
        [
            {"account": "a", "subject_id": 1, "srs_stage": 5, "hidden": False},
            {"account": "a", "subject_id": 2, "srs_stage": 1, "hidden": False},
            {"account": "a", "subject_id": 3, "srs_stage": 0, "hidden": False},
            {"account": "b", "subject_id": 4, "srs_stage": 9, "hidden": False},
        ]
    )
    index = await subject_index(db)
    assert index == {1: (1, "kanji"), 2: (1, "kanji"), 3: (2, "vocabulary"), 4: (2, "vocabulary")}
    m = await stage_matrix(db, "a", index)
    assert m[(1, "kanji", 5)] == 1 and m[(1, "kanji", 1)] == 1 and m[(1, "kanji", LOCKED)] == 0
    assert m[(2, "vocabulary", 0)] == 1 and m[(2, "vocabulary", LOCKED)] == 1
    assert levels_of(m) == [1, 2]
    assert group_counts(m, 1) == {
        "locked": 0,
        "lesson": 0,
        "apprentice": 1,
        "guru": 1,
        "master": 0,
        "enlightened": 0,
        "burned": 0,
    }
    # undo this session: kanji 1 went 4→5, kanji 2 was started (0→1), vocab 3 got unlocked
    events = [
        ev("srs_up", 1, 0, from_stage=4, to_stage=5),
        ev("srs_up", 2, 0, from_stage=0, to_stage=1),
        ev("unlocked", 3, 0),
    ]
    before = reverse_apply(m, events, index)
    assert before[(1, "kanji", 4)] == 1 and before[(1, "kanji", 5)] == 0
    assert before[(1, "kanji", 0)] == 1 and before[(1, "kanji", 1)] == 0
    assert before[(2, "vocabulary", LOCKED)] == 2 and before[(2, "vocabulary", 0)] == 0
    assert m[(1, "kanji", 5)] == 1  # the current matrix is untouched
    assert total_counts(before)["apprentice"] == 1 and total_counts(before)["guru"] == 0
    assert total_counts(m, [1])["guru"] == 1
    assert pick_levels([1, 2, 3, 4, 5, 6], 6, "around3") == [3, 4, 5, 6]
    assert pick_levels([1, 2, 3], 6, "around5") == [1, 2, 3] and pick_levels([1, 2], None, "x") == [
        1,
        2,
    ]
    assert pick_levels([1, 2, 3], 2, "all") == [1, 2, 3]
    opts = normalize_options({"sort": "desc", "levels": "bogus", "nope": 1})
    assert opts["sort"] == "desc" and opts["levels"] == "around5" and "nope" not in opts
    assert next_option("sort", "asc") == "desc" and next_option("sort", "desc") == "asc"
    assert next_option("levels", "weird") == "around3"
