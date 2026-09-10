"""File snapshots (old scraper layout) -> history -> rebuilt events."""

import json
from pathlib import Path

from wklabs.lib.importer import import_files, iter_files
from wklabs.lib.rebuild import rebuild_events


def _subject(du, meaning):
    return {
        "id": 440,
        "object": "kanji",
        "url": "https://api.wanikani.com/v2/subjects/440",
        "data_updated_at": du,
        "data": {"level": 1, "slug": "一", "characters": "一", "meanings": [{"meaning": meaning}]},
    }


def _assignment(aid, du, stage):
    return {
        "id": aid,
        "object": "assignment",
        "url": f"https://api.wanikani.com/v2/assignments/{aid}",
        "data_updated_at": du,
        "data": {
            "subject_id": 440,
            "subject_type": "kanji",
            "srs_stage": stage,
            "unlocked_at": "2024-06-30T00:00:00.000000Z",
            "started_at": "2024-07-01T00:00:00.000000Z",
            "passed_at": None,
            "burned_at": None,
            "hidden": False,
        },
    }


def _review(du, mc, mi, rc, ri):
    return {
        "id": 20,
        "object": "review_statistic",
        "url": "u",
        "data_updated_at": du,
        "data": {
            "subject_id": 440,
            "subject_type": "kanji",
            "meaning_correct": mc,
            "meaning_incorrect": mi,
            "reading_correct": rc,
            "reading_incorrect": ri,
            "percentage_correct": 80,
        },
    }


def _tree(root: Path) -> None:
    def put(rel: str, obj) -> None:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")

    m = "account_main/kanji/04xx/0440"
    put(f"{m}/2024-02/info__2024-02-12__19-36-59.json", _subject("2024-02-12T19:36:59.0Z", "One"))
    put(f"{m}/2024-07/info__2024-07-10__16-17-05.json", _subject("2024-07-10T16:17:05.0Z", "1"))
    put(f"{m}/info.json", _subject("2024-07-10T16:17:05.0Z", "1"))  # latest = last snapshot
    put(
        f"{m}/2024-07/assign__2024-07-01__10-00-00.json",
        _assignment(900, "2024-07-01T10:00:00.0Z", 1),
    )
    put(
        f"{m}/2024-07/assign__2024-07-11__10-00-00.json",
        _assignment(900, "2024-07-11T10:00:00.0Z", 2),
    )
    put(f"{m}/assign.json", _assignment(900, "2024-07-11T10:00:00.0Z", 2))
    put(
        f"{m}/2024-07/review__2024-07-01__10-00-00.json",
        _review("2024-07-01T10:00:00.0Z", 1, 0, 1, 0),
    )
    put(
        f"{m}/2024-07/review__2024-07-11__10-00-00.json",
        _review("2024-07-11T10:00:00.0Z", 2, 0, 2, 1),
    )
    put(f"{m}/2024-07/assign__2024-07-12__10-00-00.json", "{not json")  # bad
    put(f"{m}/2024-07/notes.json", {"id": 1})  # unknown name → ignored
    put(f"{m}/.DS_Store", "x")
    li = "account_light/kanji/04xx/0440"
    put(f"{li}/2024-02/info__2024-02-12__19-36-59.json", _subject("2024-02-12T19:36:59.0Z", "One"))
    put(
        f"{li}/2024-07/assign__2024-07-05__10-00-00.json",
        _assignment(901, "2024-07-05T10:00:00.0Z", 0),
    )
    (root / "not_an_account").mkdir()


def test_iter_files_picks_only_known_names(tmp_path):
    _tree(tmp_path)
    paths = [p for _, _, p in iter_files(tmp_path)]
    assert paths == sorted(paths)
    found = [(a, c, p.name) for a, c, p in iter_files(tmp_path)]
    assert len(found) == 11
    assert ("main", "info", "info.json") in found
    assert ("light", "assign", "assign__2024-07-05__10-00-00.json") in found
    assert all(n != "notes.json" for _, _, n in found)


async def test_import_then_rebuild(db, tmp_path):
    _tree(tmp_path)
    counts = await import_files(db, tmp_path, batch=3)
    # 11 files: 7 versions, 3 exact duplicates (2 latest + light's copy of the subject), 1 bad
    assert counts == {"files": 11, "inserted": 7, "duplicates": 3, "bad": 1}
    assert await db.history.count_documents({"resource": "subjects", "account": None}) == 2
    h = await db.history.find_one({"resource": "assignments", "resource_id": 901})
    assert h and h["account"] == "light" and h["run_kind"] == "import"
    assert h["source_file"].startswith("account_light/") and h["source_mtime"] is not None
    assert h["fetched_at"] is None

    # idempotent
    again = await import_files(db, tmp_path)
    assert again == {"files": 11, "inserted": 0, "duplicates": 10, "bad": 1}

    ev = await rebuild_events(db)
    assert ev == {"history": 7, "events": 3}
    kinds = sorted([e["kind"] async for e in db.events.find({})])
    assert kinds == ["reviewed", "srs_up", "subject_updated"]  # first observations are not events
    rev = await db.events.find_one({"kind": "reviewed"})
    assert rev and rev["meta"]["count"] == 1 and rev["meta"]["reading_wrong"] == 1
    assert rev["notified_at"] is not None
    upd = await db.events.find_one({"kind": "subject_updated"})
    assert upd and upd["meta"]["changed"] == ["meanings"] and upd["account"] is None
