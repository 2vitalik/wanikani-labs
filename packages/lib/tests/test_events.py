from wklabs.lib.events import derive_events


def assignment(**data):
    base = {
        "created_at": "2024-01-01T00:00:00.000000Z",
        "subject_id": 440,
        "subject_type": "kanji",
        "srs_stage": 0,
        "unlocked_at": "2024-01-01T00:00:00.000000Z",
        "started_at": None,
        "passed_at": None,
        "burned_at": None,
        "available_at": None,
        "resurrected_at": None,
        "hidden": False,
    }
    base.update(data)
    return {
        "id": 1,
        "object": "assignment",
        "url": "u",
        "data_updated_at": "2024-01-02T00:00:00.000000Z",
        "data": base,
    }


def test_baseline_has_no_events():
    assert derive_events("assignments", "main", None, assignment(), first_seen_counts=False) == []


def test_first_seen_incremental_is_unlock():
    kinds = [
        e.kind
        for e in derive_events("assignments", "main", None, assignment(), first_seen_counts=True)
    ]
    assert kinds == ["unlocked"]


def test_srs_up_and_passed():
    prev = assignment(srs_stage=4, started_at="2024-01-01T01:00:00.000000Z")
    cur = assignment(
        srs_stage=5,
        started_at="2024-01-01T01:00:00.000000Z",
        passed_at="2024-01-02T00:00:00.000000Z",
    )
    evs = derive_events("assignments", "main", prev, cur, first_seen_counts=True)
    assert [e.kind for e in evs] == ["srs_up", "passed"]
    assert evs[0].meta == {"from_stage": 4, "to_stage": 5}
    assert evs[0].subject_id == 440 and evs[0].account == "main"


def test_srs_down():
    prev = assignment(srs_stage=6)
    cur = assignment(srs_stage=4)
    assert [
        e.kind for e in derive_events("assignments", "main", prev, cur, first_seen_counts=True)
    ] == ["srs_down"]


def test_reviewed_counts():
    def rs(mc, mi, rc, ri):
        return {
            "id": 9,
            "object": "review_statistic",
            "url": "u",
            "data_updated_at": "2024-01-02T00:00:00.000000Z",
            "data": {
                "subject_id": 440,
                "subject_type": "kanji",
                "meaning_correct": mc,
                "meaning_incorrect": mi,
                "reading_correct": rc,
                "reading_incorrect": ri,
                "percentage_correct": 90,
            },
        }

    evs = derive_events(
        "review_statistics", "main", rs(10, 2, 10, 3), rs(11, 3, 11, 3), first_seen_counts=True
    )
    assert len(evs) == 1
    assert evs[0].kind == "reviewed"
    assert evs[0].meta["count"] == 1
    assert evs[0].meta["meaning_wrong"] == 1 and evs[0].meta["reading_wrong"] == 0
    assert evs[0].meta["correct"] is False
    assert (
        derive_events(
            "review_statistics", "main", rs(1, 0, 1, 0), rs(1, 0, 1, 0), first_seen_counts=True
        )
        == []
    )


def test_subject_update_diff():
    def subj(**d):
        data = {
            "level": 3,
            "slug": "x",
            "characters": "火",
            "meanings": [{"meaning": "Fire"}],
            "hidden_at": None,
            "meaning_mnemonic": "a",
        }
        data.update(d)
        return {
            "id": 440,
            "object": "kanji",
            "url": "u",
            "data_updated_at": "2024-01-02T00:00:00.000000Z",
            "data": data,
        }

    evs = derive_events(
        "subjects", None, subj(), subj(meaning_mnemonic="b"), first_seen_counts=True
    )
    assert [e.kind for e in evs] == ["subject_updated"]
    assert evs[0].meta["changed"] == ["meaning_mnemonic"]
    assert evs[0].subject_id == 440 and evs[0].subject_type == "kanji"
    assert [
        e.kind for e in derive_events("subjects", None, None, subj(), first_seen_counts=True)
    ] == ["subject_new"]


def test_user_level():
    def user(level):
        return {
            "object": "user",
            "url": "u",
            "data_updated_at": "2024-01-02T00:00:00.000000Z",
            "data": {"level": level, "username": "v", "subscription": {"active": True}},
        }

    evs = derive_events("user", "main", user(3), user(4), first_seen_counts=True)
    assert [e.kind for e in evs] == ["user_level"]
    assert evs[0].meta == {"from_level": 3, "to_level": 4}
