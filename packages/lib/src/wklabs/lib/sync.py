"""Sync engine: WaniKani -> Mongo (current state + history + events).

Per (account, resource) we keep `sync_state.updated_after` = max
`data_updated_at` seen, so a normal poll is one cheap request per endpoint.
The first run for a state is the *baseline*: versions are recorded, but no
events are derived (nothing "happened", we just started watching).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Protocol

import httpx
from bson import ObjectId
from pymongo import ReplaceOne
from pymongo.errors import BulkWriteError, DuplicateKeyError

from .api import WaniKaniClient, WaniKaniError
from .db import Db
from .events import Event, derive_events
from .resources import ACCOUNT_RESOURCES, GLOBAL_RESOURCES, RESOURCES, Resource
from .timeutil import parse_ts, utcnow

log = logging.getLogger(__name__)

Json = dict[str, Any]


class TokenSource(Protocol):
    """Where account tokens come from (`AccountRepo` in prod, `StaticTokens` in tests/CLI)."""

    async def active_tokens(self, keys: list[str] | None = None) -> dict[str, str]: ...
    async def on_auth_error(self, key: str, message: str) -> None: ...
    async def on_user_seen(self, key: str, item: Json) -> None: ...


class StaticTokens:
    def __init__(self, tokens: dict[str, str]) -> None:
        self.tokens = dict(tokens)
        self.auth_errors: dict[str, str] = {}

    async def active_tokens(self, keys: list[str] | None = None) -> dict[str, str]:
        return {k: t for k, t in self.tokens.items() if not keys or k in keys}

    async def on_auth_error(self, key: str, message: str) -> None:
        self.auth_errors[key] = message

    async def on_user_seen(self, key: str, item: Json) -> None:
        pass


@dataclass(slots=True)
class ResourceStats:
    fetched: int = 0
    new: int = 0
    changed: int = 0
    unchanged: int = 0
    events: int = 0
    baseline: bool = False
    error: str | None = None
    error_status: int | None = None  # HTTP status when the error came from WaniKani


@dataclass(slots=True)
class SyncResult:
    run_id: ObjectId
    kind: str
    started_at: datetime
    finished_at: datetime | None = None
    stats: dict[str, dict[str, ResourceStats]] = field(default_factory=dict)
    events: list[Json] = field(default_factory=list)  # inserted event docs (with _id)
    errors: list[str] = field(default_factory=list)
    requests: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def total(self, key: str) -> int:
        return sum(getattr(rs, key) for per in self.stats.values() for rs in per.values())

    def to_doc(self) -> Json:
        return {
            "_id": self.run_id,
            "kind": self.kind,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "ok": self.ok,
            "requests": self.requests,
            "events": len(self.events),
            "errors": self.errors,
            "stats": {
                scope: {name: asdict(rs) for name, rs in per.items()}
                for scope, per in self.stats.items()
            },
        }


def current_doc(resource: Resource, account: str | None, item: Json, fetched_at: datetime) -> Json:
    rid: int | str = (account or "_") if resource.singleton else item["id"]
    doc: Json = {
        "_id": rid,
        "account": account if resource.scope == "account" else None,
        "object": item.get("object"),
        "url": item.get("url"),
        "data_updated_at": item.get("data_updated_at"),
        "updated_at": parse_ts(item.get("data_updated_at")),
        "fetched_at": fetched_at,
    }
    doc.update(resource.hoist(item))
    doc["item"] = item
    return doc


def history_doc(
    resource: Resource,
    account: str | None,
    item: Json,
    *,
    fetched_at: datetime | None,
    run_kind: str,
    run_id: ObjectId | None,
    prev_data_updated_at: str | None,
) -> Json:
    rid: int | str = (account or "_") if resource.singleton else item["id"]
    return {
        "resource": resource.name,
        "account": account if resource.scope == "account" else None,
        "resource_id": rid,
        "data_updated_at": item.get("data_updated_at"),
        "updated_at": parse_ts(item.get("data_updated_at")),
        "fetched_at": fetched_at,
        "run_kind": run_kind,  # baseline | incremental | import
        "run_id": run_id,
        "prev_data_updated_at": prev_data_updated_at,
        "item": item,
    }


class SyncEngine:
    def __init__(
        self,
        db: Db,
        source: TokenSource | dict[str, str],
        *,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.db = db
        self.source: TokenSource = StaticTokens(source) if isinstance(source, dict) else source
        self.http = http
        self.clients: dict[
            str, WaniKaniClient
        ] = {}  # key -> client (rebuilt when the token changes)
        self._tokens: dict[str, str] = {}

    async def aclose(self) -> None:
        for c in self.clients.values():
            await c.aclose()
        self.clients.clear()

    async def _refresh_clients(self, keys: list[str] | None) -> list[str]:
        tokens = await self.source.active_tokens(keys)
        for key in list(self.clients):
            if self._tokens.get(key) != tokens.get(key):
                await self.clients.pop(key).aclose()
                self._tokens.pop(key, None)
        for key, tok in tokens.items():
            if key not in self.clients:
                self.clients[key] = WaniKaniClient(tok, http=self.http)
                self._tokens[key] = tok
        return sorted(tokens)

    # ------------------------------------------------------------------ run
    async def run(
        self,
        *,
        full: bool = False,
        accounts: list[str] | None = None,
        include_global: bool = True,
        include_accounts: bool = True,
        resources: list[str] | None = None,
    ) -> SyncResult:
        result = SyncResult(
            run_id=ObjectId(), kind="full" if full else "incremental", started_at=utcnow()
        )
        accs = await self._refresh_clients(accounts)
        if not accs:
            log.info("sync %s: no active accounts — nothing to do", result.kind)
            result.finished_at = utcnow()
            return result
        before = sum(c.requests_made for c in self.clients.values())

        if include_global:
            client = self.clients[accs[0]]  # subjects are identical for every token (T10)
            per: dict[str, ResourceStats] = {}
            for name in GLOBAL_RESOURCES:
                if resources and name not in resources:
                    continue
                per[name] = await self._sync_resource(None, RESOURCES[name], client, full, result)
            result.stats["_global"] = per

        if include_accounts:
            for acc in accs:
                client = self.clients[acc]
                per = {}
                for name in ACCOUNT_RESOURCES:
                    if resources and name not in resources:
                        continue
                    per[name] = await self._sync_resource(
                        acc, RESOURCES[name], client, full, result
                    )
                    if per[name].error_status in (401, 403):
                        # token revoked: stop polling this account until a new token arrives
                        await self.source.on_auth_error(acc, per[name].error or "auth error")
                        break
                result.stats[acc] = per

        result.requests = sum(c.requests_made for c in self.clients.values()) - before
        result.finished_at = utcnow()
        await self.db.sync_runs.insert_one(result.to_doc())
        log.info(
            "sync %s done in %.1fs: %d fetched, %d new, %d changed, %d events, %d requests%s",
            result.kind,
            (result.finished_at - result.started_at).total_seconds(),
            result.total("fetched"),
            result.total("new"),
            result.total("changed"),
            len(result.events),
            result.requests,
            f", errors: {result.errors}" if result.errors else "",
        )
        return result

    # ------------------------------------------------------- one resource
    async def _sync_resource(
        self,
        account: str | None,
        res: Resource,
        client: WaniKaniClient,
        full: bool,
        result: SyncResult,
    ) -> ResourceStats:
        stats = ResourceStats()
        state_id = f"{account or '_'}:{res.name}"
        state = await self.db.sync_state.find_one({"_id": state_id}) or {}
        baseline = not state.get("last_ok_at")
        stats.baseline = baseline
        run_kind = "baseline" if baseline else "incremental"
        fetched_at = utcnow()
        max_updated: str | None = state.get("updated_after")
        params: dict[str, Any] = dict(res.params)
        if not full and not baseline and state.get("updated_after") and not res.singleton:
            params["updated_after"] = state["updated_after"]
        etag: str | None = None
        try:
            if res.singleton:
                resp = await client.get(res.endpoint, etag=None if full else state.get("etag"))
                etag = resp.etag
                if resp.not_modified or resp.data is None:
                    stats.unchanged += 1
                else:
                    stats.fetched += 1
                    await self._store_items(
                        account, res, [resp.data], fetched_at, run_kind, result, stats
                    )
                    du = resp.data.get("data_updated_at")
                    if du and (max_updated is None or du > max_updated):
                        max_updated = du
            else:
                async for page in client.iter_pages(res.endpoint, params):
                    items = page.get("data") or []
                    stats.fetched += len(items)
                    await self._store_items(
                        account, res, items, fetched_at, run_kind, result, stats
                    )
                    for it in items:
                        du = it.get("data_updated_at")
                        if du and (max_updated is None or du > max_updated):
                            max_updated = du
        except WaniKaniError as exc:
            stats.error = str(exc)
            stats.error_status = exc.status
        except Exception as exc:
            log.exception("sync %s/%s failed", account, res.name)
            stats.error = f"{type(exc).__name__}: {exc}"

        now = utcnow()
        upd: Json = {"last_run_at": now, "last_error": stats.error, "run_id": result.run_id}
        if stats.error is None:
            upd["last_ok_at"] = now
            upd["updated_after"] = max_updated
            if res.singleton:
                upd["etag"] = etag
        else:
            result.errors.append(f"{state_id}: {stats.error}")
        await self.db.sync_state.update_one({"_id": state_id}, {"$set": upd}, upsert=True)
        return stats

    async def _store_items(
        self,
        account: str | None,
        res: Resource,
        items: list[Json],
        fetched_at: datetime,
        run_kind: str,
        result: SyncResult,
        stats: ResourceStats,
    ) -> None:
        if not items:
            return
        coll = self.db.current(res.name)
        acc_key = account if res.scope == "account" else None
        if res.singleton:
            ids: list[Any] = [account or "_"]
        else:
            ids = [it["id"] for it in items]
        existing: dict[Any, Json] = {}
        async for d in coll.find({"_id": {"$in": ids}}):
            existing[d["_id"]] = d

        writes: list[ReplaceOne[Json]] = []
        hist_docs: list[Json] = []
        pending: list[tuple[Json, Json | None]] = []  # (history_doc, prev_item)
        for it in items:
            rid: Any = (account or "_") if res.singleton else it["id"]
            prev = existing.get(rid)
            if prev is not None and prev.get("data_updated_at") == it.get("data_updated_at"):
                stats.unchanged += 1
                continue
            if prev is None:
                stats.new += 1
            else:
                stats.changed += 1
            writes.append(
                ReplaceOne({"_id": rid}, current_doc(res, account, it, fetched_at), upsert=True)
            )
            h = history_doc(
                res,
                account,
                it,
                fetched_at=fetched_at,
                run_kind=run_kind,
                run_id=result.run_id,
                prev_data_updated_at=prev.get("data_updated_at") if prev else None,
            )
            hist_docs.append(h)
            pending.append((h, prev.get("item") if prev else None))
        if not writes:
            return
        await coll.bulk_write(writes, ordered=False)
        if res.name == "user" and account is not None:
            await self.source.on_user_seen(account, items[0])

        # history: unique on version — duplicates mean "already recorded" (e.g. re-sync)
        inserted_ids: dict[int, ObjectId] = {}
        try:
            r = await self.db.history.insert_many(hist_docs, ordered=False)
            inserted_ids = dict(enumerate(r.inserted_ids))
        except BulkWriteError as exc:
            dup_idx = {e["index"] for e in exc.details.get("writeErrors", []) if e["code"] == 11000}
            for i, h in enumerate(hist_docs):
                if i not in dup_idx and "_id" in h:
                    inserted_ids[i] = h["_id"]
            log.debug("history: %d duplicate versions skipped", len(dup_idx))

        ev_docs: list[Json] = []
        for i, (h, prev_item) in enumerate(pending):
            if i not in inserted_ids:
                continue  # version already known → events already derived
            events: list[Event] = derive_events(
                res.name,
                acc_key,
                prev_item,
                h["item"],
                first_seen_counts=(run_kind == "incremental"),
            )
            for ev in events:
                d = ev.to_doc()
                d.update(
                    {
                        "history_id": inserted_ids[i],
                        "run_id": result.run_id,
                        "fetched_at": fetched_at,
                        "notified_at": None,
                    }
                )
                ev_docs.append(d)
        if ev_docs:
            try:
                r2 = await self.db.events.insert_many(ev_docs, ordered=False)
                for d, oid in zip(ev_docs, r2.inserted_ids, strict=True):
                    d["_id"] = oid
                result.events.extend(ev_docs)
            except BulkWriteError as exc:
                dup_idx = {e["index"] for e in exc.details.get("writeErrors", [])}
                result.events.extend(d for i, d in enumerate(ev_docs) if i not in dup_idx)
            except DuplicateKeyError:
                pass
            stats.events += len(ev_docs)
