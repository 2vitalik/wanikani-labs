"""Study sessions derived from events: instants (`reviewed` + `started`) chained by a gap.

Pure `split_sessions` runs both live (`ingest` after every sync) and in
`rebuild` (replay of `events`), so boundaries are reproducible. A session
closes only once a *successful* poll proved the silence (T32 §2) or the user
pressed ⏹. Sessions are keyed by (account, gap): two routes with different
gaps see two independent session streams.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from .db import Db
from .timeutil import utcnow

log = logging.getLogger(__name__)
Json = dict[str, Any]

INSTANT_KINDS: tuple[str, ...] = ("reviewed", "started")
OPEN, CLOSED = "open", "closed"
BY_AUTO, BY_USER = "auto", "user"
DEFAULT_GAP = 15  # minutes (T31 §4)
LOOKBACK = timedelta(hours=24)  # no sessions yet: how far back the first ingest looks
EDGE = timedelta(seconds=1)  # srs moves and reviews of one item differ by milliseconds


def split_sessions(
    instants: list[datetime], gap: timedelta
) -> list[tuple[datetime, datetime, int]]:
    """Chain sorted instants; a pause longer than `gap` starts a new session → (start, end, n)."""
    out: list[tuple[datetime, datetime, int]] = []
    start: datetime | None = None
    prev: datetime | None = None
    n = 0
    for t in sorted(set(instants)):
        if start is not None and prev is not None and t - prev > gap:
            out.append((start, prev, n))
            start, n = None, 0
        if start is None:
            start = t
        prev = t
        n += 1
    if start is not None and prev is not None:
        out.append((start, prev, n))
    return out


@dataclass(slots=True)
class Session:
    id: ObjectId
    account: str
    gap: int  # minutes
    started_at: datetime
    last_at: datetime
    n_instants: int
    status: str = OPEN
    closed_at: datetime | None = None
    closed_by: str | None = None
    stats: Json | None = None
    delivered: list[ObjectId] = field(default_factory=list)
    reported_at: datetime | None = None
    rebuilt: bool = False

    @classmethod
    def from_doc(cls, d: Json) -> Session:
        return cls(
            id=d["_id"],
            account=str(d["account"]),
            gap=int(d["gap"]),
            started_at=d["started_at"],
            last_at=d["last_at"],
            n_instants=int(d.get("n_instants") or 0),
            status=str(d.get("status") or OPEN),
            closed_at=d.get("closed_at"),
            closed_by=d.get("closed_by"),
            stats=d.get("stats"),
            delivered=list(d.get("delivered") or []),
            reported_at=d.get("reported_at"),
            rebuilt=bool(d.get("rebuilt")),
        )

    @property
    def is_open(self) -> bool:
        return self.status == OPEN

    @property
    def duration(self) -> timedelta:
        return self.last_at - self.started_at

    @property
    def key(self) -> str:
        return f"session:{self.id}"

    @property
    def window(self) -> tuple[datetime, datetime]:
        return self.started_at - EDGE, self.last_at + EDGE


class SessionRepo:
    def __init__(self, db: Db) -> None:
        self.db = db

    # ---------------------------------------------------------------- reads
    async def get(self, session_id: ObjectId) -> Session | None:
        d = await self.db.sessions.find_one({"_id": session_id})
        return Session.from_doc(d) if d else None

    async def current(self, account: str, gap: int) -> Session | None:
        d = await self.db.sessions.find_one({"account": account, "gap": gap, "status": OPEN})
        return Session.from_doc(d) if d else None

    async def last(self, account: str, gap: int) -> Session | None:
        d = await self.db.sessions.find_one(
            {"account": account, "gap": gap}, sort=[("started_at", -1)]
        )
        return Session.from_doc(d) if d else None

    async def recent(self, account: str, gap: int, *, limit: int = 10) -> list[Session]:
        """Closed sessions, newest first."""
        return [
            Session.from_doc(d)
            async for d in self.db.sessions.find(
                {"account": account, "gap": gap, "status": CLOSED},
                sort=[("started_at", -1)],
                limit=limit,
            )
        ]

    async def pending(self, account: str, gap: int) -> list[Session]:
        """Closed, not yet reported to every route (oldest first)."""
        return [
            Session.from_doc(d)
            async for d in self.db.sessions.find(
                {"account": account, "gap": gap, "status": CLOSED, "reported_at": None},
                sort=[("started_at", 1)],
            )
        ]

    async def instants(self, account: str, after: datetime | None = None) -> list[datetime]:
        q: Json = {"account": account, "kind": {"$in": list(INSTANT_KINDS)}}
        if after is not None:
            q["at"] = {"$gt": after}
        values = await self.db.events.distinct("at", q)
        return sorted(v for v in values if isinstance(v, datetime))

    async def events(self, session: Session) -> list[Json]:
        """Every account event inside the session window (reviews, moves, lessons, milestones)."""
        lo, hi = session.window
        return [
            d
            async for d in self.db.events.find(
                {"account": session.account, "at": {"$gte": lo, "$lte": hi}}, sort=[("at", 1)]
            )
        ]

    # --------------------------------------------------------------- writes
    async def _open(self, account: str, gap: int, at: datetime, now: datetime) -> Session:
        doc: Json = {
            "_id": ObjectId(),
            "account": account,
            "gap": gap,
            "started_at": at,
            "last_at": at,
            "n_instants": 1,
            "status": OPEN,
            "delivered": [],
            "reported_at": None,
            "created_at": now,
            "updated_at": now,
        }
        await self.db.sessions.insert_one(doc)
        log.info("session %s/%d opened at %s", account, gap, at)
        return Session.from_doc(doc)

    async def _extend(self, s: Session, now: datetime) -> None:
        await self.db.sessions.update_one(
            {"_id": s.id},
            {"$set": {"last_at": s.last_at, "n_instants": s.n_instants, "updated_at": now}},
        )

    async def _close(self, s: Session, now: datetime, by: str) -> Session:
        s.status, s.closed_at, s.closed_by = CLOSED, now, by
        await self.db.sessions.update_one(
            {"_id": s.id},
            {
                "$set": {
                    "last_at": s.last_at,
                    "n_instants": s.n_instants,
                    "status": CLOSED,
                    "closed_at": now,
                    "closed_by": by,
                    "updated_at": now,
                }
            },
        )
        log.info(
            "session %s/%d closed (%s): %s → %s, %d instants",
            s.account,
            s.gap,
            by,
            s.started_at,
            s.last_at,
            s.n_instants,
        )
        return s

    async def ingest(self, account: str, gap: int, *, now: datetime | None = None) -> list[Session]:
        """Fold new instants into the open session (or open new ones); returns touched sessions.

        A pause longer than the gap between two instants closes the earlier session right
        away — the later event itself proves the silence."""
        now = now or utcnow()
        cur = await self.current(account, gap)
        if cur is not None:
            floor = cur.last_at
        else:
            last = await self.last(account, gap)
            floor = last.last_at if last else now - LOOKBACK
        new = await self.instants(account, floor)
        if not new:
            return []
        gap_td = timedelta(minutes=gap)
        touched: list[Session] = []
        for t in new:
            if cur is not None and t - cur.last_at <= gap_td:
                cur.last_at, cur.n_instants = t, cur.n_instants + 1
                continue
            if cur is not None:
                touched.append(await self._close(cur, now, BY_AUTO))
            cur = await self._open(account, gap, t, now)
        assert cur is not None
        if cur.is_open:
            await self._extend(cur, now)
        touched.append(cur)
        return touched

    async def close_idle(
        self, account: str, gap: int, last_ok_at: datetime | None, *, now: datetime | None = None
    ) -> Session | None:
        """Close the open session once a successful poll is `gap` past its last instant."""
        if last_ok_at is None:
            return None
        cur = await self.current(account, gap)
        if cur is None or last_ok_at - cur.last_at < timedelta(minutes=gap):
            return None
        return await self._close(cur, now or utcnow(), BY_AUTO)

    async def close_now(self, session_id: ObjectId, *, by: str = BY_USER) -> Session | None:
        s = await self.get(session_id)
        if s is None or not s.is_open:
            return None
        return await self._close(s, utcnow(), by)

    async def set_stats(self, session_id: ObjectId, stats: Json) -> None:
        await self.db.sessions.update_one({"_id": session_id}, {"$set": {"stats": stats}})

    async def mark_delivered(self, session_id: ObjectId, route_id: ObjectId) -> None:
        await self.db.sessions.update_one(
            {"_id": session_id}, {"$addToSet": {"delivered": route_id}}
        )

    async def mark_reported(self, session_ids: list[ObjectId], now: datetime | None = None) -> None:
        if session_ids:
            await self.db.sessions.update_many(
                {"_id": {"$in": session_ids}}, {"$set": {"reported_at": now or utcnow()}}
            )

    async def reopen_guard(self, session_id: ObjectId) -> Session | None:
        """Live message pressed ⏹ twice: return the session as it is now (no-op helper)."""
        d = await self.db.sessions.find_one_and_update(
            {"_id": session_id, "status": OPEN},
            {"$set": {"updated_at": utcnow()}},
            return_document=ReturnDocument.AFTER,
        )
        return Session.from_doc(d) if d else None

    # -------------------------------------------------------------- rebuild
    async def rebuild(
        self, account: str, gap: int, *, now: datetime | None = None
    ) -> dict[str, int]:
        """Drop the (account, gap) sessions and replay every instant; history is never re-sent.

        The last session stays open when its last instant is still within the gap."""
        now = now or utcnow()
        await self.db.sessions.delete_many({"account": account, "gap": gap})
        instants = await self.instants(account)
        parts = split_sessions(instants, timedelta(minutes=gap))
        docs: list[Json] = []
        for start, end, n in parts:
            still_open = now - end < timedelta(minutes=gap)
            docs.append(
                {
                    "_id": ObjectId(),
                    "account": account,
                    "gap": gap,
                    "started_at": start,
                    "last_at": end,
                    "n_instants": n,
                    "status": OPEN if still_open else CLOSED,
                    "closed_at": None if still_open else end,
                    "closed_by": None if still_open else BY_AUTO,
                    "delivered": [],
                    "reported_at": None if still_open else now,
                    "rebuilt": True,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        if docs:
            await self.db.sessions.insert_many(docs)
        log.info(
            "sessions %s/%d rebuilt: %d instants → %d sessions",
            account,
            gap,
            len(instants),
            len(docs),
        )
        return {"instants": len(instants), "sessions": len(docs)}
