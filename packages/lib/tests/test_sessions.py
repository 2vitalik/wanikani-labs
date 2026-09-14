"""Sessions: pure split, live ingest/close rules, ⏹ end now, rebuild, reports."""

from datetime import UTC, datetime, timedelta

from bson import ObjectId

from wklabs.lib.reports import ReportRepo, text_hash
from wklabs.lib.sessions import BY_AUTO, BY_USER, CLOSED, OPEN, SessionRepo, split_sessions

T0 = datetime(2026, 9, 13, 17, 52, tzinfo=UTC)
GAP = timedelta(minutes=15)


def m(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def test_split_sessions():
    assert split_sessions([], GAP) == []
    assert split_sessions([m(0)], GAP) == [(m(0), m(0), 1)]
    one = split_sessions([m(0), m(1), m(15), m(30)], GAP)  # pauses of exactly 15 min stay
    assert one == [(m(0), m(30), 4)]
    two = split_sessions([m(30), m(0), m(1), m(16.01), m(0)], GAP)  # unsorted, duplicate
    assert two == [(m(0), m(1), 2), (m(16.01), m(30), 2)]
    assert split_sessions([m(0), m(200), m(400)], GAP) == [
        (m(0), m(0), 1),
        (m(200), m(200), 1),
        (m(400), m(400), 1),
    ]


async def _events(db, key: str, at: list[datetime], kind: str = "reviewed", sid: int = 1):
    await db.events.insert_many(
        [
            {
                "kind": kind,
                "at": t,
                "account": key,
                "subject_id": sid + i,
                "subject_type": "kanji",
                "meta": {"count": 1, "correct": True, "meaning_wrong": 0, "reading_wrong": 0},
                "history_id": ObjectId(),
                "notified_at": None,
            }
            for i, t in enumerate(at)
        ]
    )


async def test_ingest_extend_close_and_new(db):
    repo = SessionRepo(db)
    key = "07fff792"
    await _events(db, key, [m(0), m(1), m(3)])
    touched = await repo.ingest(key, 15, now=m(5))
    assert len(touched) == 1 and touched[0].is_open and touched[0].n_instants == 3
    assert touched[0].started_at == m(0) and touched[0].last_at == m(3)
    assert await repo.ingest(key, 15, now=m(6)) == []  # nothing new
    # a poll that finds no events cannot close the session before the gap has passed
    assert await repo.close_idle(key, 15, m(17), now=m(17)) is None
    await _events(db, key, [m(10)], sid=10)
    (cur,) = await repo.ingest(key, 15, now=m(12))
    assert cur.is_open and cur.n_instants == 4 and cur.last_at == m(10)
    # a successful poll ≥ gap after the last instant closes it
    closed = await repo.close_idle(key, 15, m(25), now=m(25))
    assert closed and closed.status == CLOSED and closed.closed_by == BY_AUTO
    assert await repo.current(key, 15) is None
    assert [s.id for s in await repo.pending(key, 15)] == [closed.id]
    # later events beyond the gap open a new session; an inner pause > gap splits at once
    await _events(db, key, [m(60), m(61), m(90)], sid=20)
    touched = await repo.ingest(key, 15, now=m(95))
    assert [(s.status, s.n_instants) for s in touched] == [(CLOSED, 2), (OPEN, 1)]
    assert touched[0].closed_by == BY_AUTO and touched[1].started_at == m(90)
    # a different gap is an independent stream
    assert await repo.current(key, 30) is None
    got = await repo.ingest(key, 30, now=m(95))  # 10 → 60 is > 30 min: two sessions
    assert [(s.status, s.n_instants, s.gap) for s in got] == [(CLOSED, 4, 30), (OPEN, 3, 30)]
    # events of the session window
    evs = await repo.events(touched[0])
    assert [e["at"] for e in evs] == [m(60), m(61)]


async def test_end_now_and_reporting(db):
    repo = SessionRepo(db)
    key = "07fff792"
    await _events(db, key, [m(0), m(1)])
    (cur,) = await repo.ingest(key, 15, now=m(2))
    ended = await repo.close_now(cur.id)
    assert ended and ended.closed_by == BY_USER and await repo.close_now(cur.id) is None
    # events within the gap after ⏹ start a new session, they do not reopen the old one
    await _events(db, key, [m(5)], sid=5)
    (new,) = await repo.ingest(key, 15, now=m(6))
    assert new.id != cur.id and new.is_open and new.started_at == m(5)
    rid = ObjectId()
    await repo.mark_delivered(ended.id, rid)
    await repo.mark_reported([ended.id], m(7))
    got = await repo.get(ended.id)
    assert got and got.delivered == [rid] and got.reported_at == m(7)
    assert await repo.pending(key, 15) == []
    await repo.set_stats(ended.id, {"n_items": 2})
    got = await repo.get(ended.id)
    assert got and got.stats == {"n_items": 2} and got.key == f"session:{ended.id}"
    assert [s.id for s in await repo.recent(key, 15)] == [ended.id]
    # reports: one per (route, key), edited in place
    reports = ReportRepo(db)
    assert await reports.get(rid, ended.key) is None
    rep = await reports.upsert(
        rid, ended.key, chat_id=42, thread_id=None, message_ids=[5], final=False, text_hash="a"
    )
    rep2 = await reports.upsert(
        rid, ended.key, chat_id=42, thread_id=None, message_ids=[5], final=True, text_hash="b"
    )
    assert rep2.id == rep.id and rep2.final and rep2.message_id == 5 and rep2.sent_at == rep.sent_at
    assert len(await reports.for_key(ended.key)) == 1
    assert text_hash(["x"]) != text_hash(["y"]) and len(text_hash(["x"])) == 16


async def test_rebuild_marks_history_reported(db):
    repo = SessionRepo(db)
    key = "07fff792"
    await _events(db, key, [m(0), m(1), m(40), m(41), m(42)])
    await _events(db, key, [m(41)], kind="started", sid=50)  # same instant, no double count
    res = await repo.rebuild(key, 15, now=m(100))
    assert res == {"instants": 5, "sessions": 2}
    sessions = await repo.recent(key, 15)
    assert [(s.n_instants, s.status, s.rebuilt) for s in sessions] == [
        (3, CLOSED, True),
        (2, CLOSED, True),
    ]
    assert all(s.reported_at == m(100) for s in sessions) and await repo.pending(key, 15) == []
    # the last one stays open when it is still within the gap
    res = await repo.rebuild(key, 15, now=m(50))
    cur = await repo.current(key, 15)
    assert res["sessions"] == 2 and cur and cur.n_instants == 3 and cur.reported_at is None
    assert await repo.rebuild("nobody", 15) == {"instants": 0, "sessions": 0}
