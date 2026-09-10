"""Pre-restructure raw dumps -> history -> rebuilt events."""

import json
from pathlib import Path

from wklabs.lib.importer_raw import import_raw, parse_account_map
from wklabs.lib.rebuild import rebuild_events


def _page(items):
    return {
        "object": "collection",
        "url": "u",
        "pages": {"per_page": 500, "next_url": None, "previous_url": None},
        "total_count": len(items),
        "data_updated_at": None,
        "data": items,
    }


def _assignment(aid, du, stage):
    return {
        "id": aid,
        "object": "assignment",
        "url": "u",
        "data_updated_at": du,
        "data": {
            "subject_id": 440,
            "subject_type": "kanji",
            "srs_stage": stage,
            "unlocked_at": "2024-03-01T00:00:00.000000Z",
            "started_at": "2024-03-02T00:00:00.000000Z",
            "passed_at": None,
            "burned_at": None,
            "hidden": False,
        },
    }


def _subject(du, meaning):
    return {
        "id": 440,
        "object": "kanji",
        "url": "u",
        "data_updated_at": du,
        "data": {"level": 1, "slug": "一", "characters": "一", "meanings": [{"meaning": meaning}]},
    }


def _tree(root: Path) -> None:
    def put(rel, obj):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")

    a, b, c = "2024-04-01T00:00:00.0Z", "2024-04-02T00:00:00.0Z", "2024-04-09T00:00:00.0Z"
    put(
        "data1-04_08/assignments/raw/assignments [p1].json",
        _page([_assignment(900, a, 1), _assignment(901, b, 1)]),
    )
    put(
        "data1-04_09/assignments/raw/assignments [p1].json",
        _page([_assignment(900, a, 1), _assignment(901, c, 2)]),
    )
    put("data1-04_08/items/raw/kanji [p1].json", _page([_subject(a, "One")]))
    put(
        "data1-04_08/summary/raw/summary [p1].json",
        {
            "object": "report",
            "url": "u",
            "data_updated_at": a,
            "data": {"lessons": [], "reviews": [], "next_reviews_at": None},
        },
    )
    put(
        "data1-04_08/level_progressions/raw/level_progressions [p1].json",
        _page(
            [
                {
                    "id": 5,
                    "object": "level_progression",
                    "url": "u",
                    "data_updated_at": a,
                    "data": {
                        "level": 1,
                        "unlocked_at": a,
                        "started_at": a,
                        "passed_at": None,
                        "completed_at": None,
                        "abandoned_at": None,
                    },
                }
            ]
        ),
    )
    put("data1-04_08/assignments/raw/bad.json", "{oops")
    put("data2-04_09/assignments/raw/assignments [p1].json", _page([_assignment(950, c, 0)]))
    put("data.v1/kanji/04xx/0440/2024-04/2024-04-09__05-30-26.json", _subject(c, "1"))
    put(
        "data.v1/kanji/04xx/0440/2024-04/2024-04-01__05-30-26.json", _subject(a, "One")
    )  # dup of the page
    put(
        "data.v1/kanji/04xx/0440/2024-04/2024-04-10__05-30-26.json", _assignment(960, c, 0)
    )  # → default account
    put("new_data/kanji/10xx/1039/info.json", _subject(a, "x"))  # unknown layout → skipped


def test_parse_account_map():
    assert parse_account_map("data1=main, data2=light,") == {"data1": "main", "data2": "light"}


async def test_import_raw_then_rebuild(db, tmp_path):
    _tree(tmp_path)
    counts = await import_raw(db, tmp_path, batch=4)
    assert counts == {
        "files": 10,
        "objects": 11,
        "inserted": 9,
        "duplicates": 2,
        "bad": 1,
        "skipped_files": 1,
    }
    summ = await db.history.find_one({"resource": "summary"})
    assert summ and summ["account"] == "main" and summ["resource_id"] == "main"
    assert (await db.history.find_one({"resource": "assignments", "resource_id": 950}))[
        "account"
    ] == "light"
    assert (await db.history.find_one({"resource": "assignments", "resource_id": 960}))[
        "account"
    ] == "main"
    assert await db.history.count_documents({"resource": "subjects", "account": None}) == 2
    assert (await db.history.find_one({"resource": "subjects"}))["source_file"].startswith("data")

    again = await import_raw(db, tmp_path)
    assert again["inserted"] == 0 and again["duplicates"] == 11

    ev = await rebuild_events(db)
    assert ev == {"history": 9, "events": 2}
    kinds = sorted([e["kind"] async for e in db.events.find({})])
    assert kinds == ["srs_up", "subject_updated"]
