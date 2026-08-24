"""Sync engine against a fake WaniKani (httpx MockTransport) and a real local Mongo."""

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from wklabs.lib.rebuild import rebuild_events
from wklabs.lib.sync import SyncEngine


class FakeWK:
    """Minimal WaniKani: subjects + assignments + review_statistics + user + summary."""

    def __init__(self):
        self.subjects = [
            self.subject(1, "radical", "一", "Ground"),
            self.subject(2, "kanji", "一", "One"),
        ]
        self.assignments = {}
        self.review_stats = {}
        self.calls = []
        self.ts = "2026-08-01T00:00:00.000000Z"

    @staticmethod
    def subject(sid, typ, chars, meaning, updated="2026-07-01T00:00:00.000000Z"):
        return {
            "id": sid,
            "object": typ,
            "url": f"https://api.wanikani.com/v2/subjects/{sid}",
            "data_updated_at": updated,
            "data": {
                "level": 1,
                "slug": chars,
                "characters": chars,
                "meanings": [{"meaning": meaning, "primary": True}],
                "readings": [],
                "hidden_at": None,
                "lesson_position": 1,
                "document_url": "https://www.wanikani.com/x",
                "spaced_repetition_system_id": 1,
            },
        }

    def set_assignment(self, aid, sid, stage, **extra):
        d = {
            "created_at": "2026-07-02T00:00:00.000000Z",
            "subject_id": sid,
            "subject_type": "kanji" if sid == 2 else "radical",
            "srs_stage": stage,
            "unlocked_at": "2026-07-02T00:00:00.000000Z",
            "started_at": None,
            "passed_at": None,
            "burned_at": None,
            "available_at": None,
            "resurrected_at": None,
            "hidden": False,
        }
        d.update(extra)
        self.assignments[aid] = {
            "id": aid,
            "object": "assignment",
            "url": "u",
            "data_updated_at": self.ts,
            "data": d,
        }

    def set_review_stats(self, rid, sid, mc, mi, rc, ri):
        self.review_stats[rid] = {
            "id": rid,
            "object": "review_statistic",
            "url": "u",
            "data_updated_at": self.ts,
            "data": {
                "created_at": "2026-07-02T00:00:00.000000Z",
                "subject_id": sid,
                "subject_type": "kanji" if sid == 2 else "radical",
                "meaning_correct": mc,
                "meaning_incorrect": mi,
                "reading_correct": rc,
                "reading_incorrect": ri,
                "meaning_max_streak": 1,
                "reading_max_streak": 1,
                "meaning_current_streak": 1,
                "reading_current_streak": 1,
                "percentage_correct": 90,
                "hidden": False,
            },
        }

    def collection(self, items, updated_after):
        if updated_after:
            items = [i for i in items if i["data_updated_at"] > updated_after]
        return {
            "object": "collection",
            "url": "u",
            "pages": {"per_page": 1000, "next_url": None, "previous_url": None},
            "total_count": len(items),
            "data_updated_at": None,
            "data": items,
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        u = urlparse(str(request.url))
        q = parse_qs(u.query)
        ua = (q.get("updated_after") or [None])[0]
        self.calls.append((u.path, ua))
        path = u.path.removeprefix("/v2/")
        match path:
            case "subjects":
                return httpx.Response(200, json=self.collection(self.subjects, ua))
            case "assignments":
                return httpx.Response(
                    200, json=self.collection(list(self.assignments.values()), ua)
                )
            case "review_statistics":
                return httpx.Response(
                    200, json=self.collection(list(self.review_stats.values()), ua)
                )
            case "user":
                if request.headers.get("If-None-Match") == 'W/"u1"':
                    return httpx.Response(304, headers={"etag": 'W/"u1"'})
                return httpx.Response(
                    200,
                    headers={"etag": 'W/"u1"'},
                    json={
                        "object": "user",
                        "url": "u",
                        "data_updated_at": self.ts,
                        "data": {
                            "username": "tester",
                            "level": 1,
                            "subscription": {
                                "active": True,
                                "max_level_granted": 60,
                                "type": "lifetime",
                            },
                        },
                    },
                )
            case "summary":
                return httpx.Response(
                    200,
                    json={
                        "object": "report",
                        "url": "u",
                        "data_updated_at": self.ts,
                        "data": {
                            "lessons": [],
                            "next_reviews_at": None,
                            "reviews": [{"available_at": self.ts, "subject_ids": [1, 2]}],
                        },
                    },
                )
            case _:
                return httpx.Response(200, json=self.collection([], ua))


@pytest.fixture
def wk():
    return FakeWK()


@pytest.fixture
async def engine(db, wk):
    http = httpx.AsyncClient(transport=httpx.MockTransport(wk.handler))
    eng = SyncEngine(db, {"main": "tok"}, http=http)
    yield eng
    await eng.aclose()
    await http.aclose()


async def test_baseline_then_incremental(db, wk, engine):
    wk.set_assignment(10, 2, 1, started_at="2026-07-03T00:00:00.000000Z")
    wk.set_review_stats(20, 2, 1, 0, 1, 0)

    r1 = await engine.run()
    assert r1.ok and r1.events == []
    assert r1.stats["main"]["assignments"].baseline is True
    assert await db.current("assignments").count_documents({}) == 1
    assert (
        await db.history.count_documents({}) == 2 + 1 + 1 + 1 + 1
    )  # subj, assign, rs, user, summary

    # nothing changed → cheap incremental: updated_after used, no writes
    r2 = await engine.run()
    assert r2.ok and r2.total("new") == 0 and r2.total("changed") == 0
    assert r2.stats["main"]["assignments"].fetched == 0
    assert r2.stats["main"]["user"].fetched == 0  # 304 via ETag
    assert r2.stats["main"]["summary"].unchanged == 1  # same data_updated_at
    ua = [ua for p, ua in wk.calls if p.endswith("/assignments")][-1]
    assert ua == "2026-08-01T00:00:00.000000Z"

    # a review: stage 1 -> 2, stats +1 correct; a new assignment unlocked
    wk.ts = "2026-08-02T00:00:00.000000Z"
    wk.set_assignment(10, 2, 2, started_at="2026-07-03T00:00:00.000000Z")
    wk.set_review_stats(20, 2, 2, 0, 2, 1)
    wk.set_assignment(11, 1, 0)
    r3 = await engine.run()
    kinds = sorted(e["kind"] for e in r3.events)
    assert kinds == ["reviewed", "srs_up", "unlocked"]
    rev = next(e for e in r3.events if e["kind"] == "reviewed")
    assert rev["meta"]["count"] == 1 and rev["meta"]["reading_wrong"] == 1
    assert rev["subject_id"] == 2 and rev["notified_at"] is None
    assert await db.events.count_documents({}) == 3

    # replaying the same state changes nothing (idempotent)
    r4 = await engine.run(full=True)
    assert r4.events == [] and await db.events.count_documents({}) == 3
    hist_before = await db.history.count_documents({})

    # rebuild reproduces the same events from history
    counts = await rebuild_events(db)
    assert counts["events"] == 3
    assert await db.events.count_documents({"notified_at": None}) == 0
    assert await db.history.count_documents({}) == hist_before
    run = await db.sync_runs.find_one(sort=[("started_at", -1)])
    assert run and run["ok"] and run["kind"] == "full"


async def test_error_in_one_resource_does_not_block_others(db, wk, engine):
    def bad(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/review_statistics"):
            return httpx.Response(401, json={"error": "Unauthorized. Nice try.", "code": 401})
        return wk.handler(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(bad))
    eng = SyncEngine(db, {"main": "tok"}, http=http)
    try:
        r = await eng.run()
    finally:
        await eng.aclose()
        await http.aclose()
    assert not r.ok
    assert r.stats["main"]["review_statistics"].error
    assert r.stats["main"]["assignments"].error is None
    st = await db.sync_state.find_one({"_id": "main:review_statistics"})
    assert st and st.get("last_ok_at") is None and st["last_error"]
