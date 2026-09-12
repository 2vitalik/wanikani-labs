"""WaniKani accounts in Mongo: identity (`wk_id`), encrypted token, owner, status.

The account *key* (`_id`) is `wk_id[:8]`, derived from WaniKani's immutable
user id, so the same account always maps to the same key: history stitches
back together after remove/re-add, on any server. The key is the `account`
field of every per-account document (assignments, history, events, …).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from pymongo import ReturnDocument

from .api import WaniKaniClient, WaniKaniError
from .crypto import CipherError, TokenCipher
from .db import EVENTS, HISTORY, SYNC_STATE, TG_ROUTES, Db
from .resources import RESOURCES
from .timeutil import utcnow

log = logging.getLogger(__name__)
Json = dict[str, Any]

ACTIVE = "active"
PAUSED = "paused"
AUTH_ERROR = "auth_error"  # WaniKani rejected the token (401/403)
KEY_ERROR = "key_error"  # token cannot be decrypted (WKLABS_SECRET_KEY changed)
REMOVED = "removed"  # hidden from the UI, data kept
PURGED = "purged"  # per-account data deleted
STATUS_EMOJI = {
    ACTIVE: "🟢",
    PAUSED: "⏸",
    AUTH_ERROR: "⚠️",
    KEY_ERROR: "⚠️",
    REMOVED: "🗑",
    PURGED: "🗑",
}

_TOKEN_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def looks_like_token(text: str | None) -> bool:
    return bool(text and _TOKEN_RE.match(text.strip()))


def key_for(wk_id: str, length: int = 8) -> str:
    return wk_id.replace("-", "")[:length].lower()


def token_hint(token: str) -> str:
    return token[-4:]


class InvalidTokenError(Exception):
    """WaniKani rejected the token (401/403)."""


@dataclass(slots=True)
class WkIdentity:
    wk_id: str
    username: str
    level: int
    subscription_type: str | None
    max_level: int | None

    @classmethod
    def from_user(cls, item: Json) -> WkIdentity:
        d = item.get("data") or {}
        sub = d.get("subscription") or {}
        return cls(
            wk_id=str(d["id"]),
            username=str(d.get("username") or ""),
            level=int(d.get("level") or 0),
            subscription_type=sub.get("type"),
            max_level=sub.get("max_level_granted"),
        )


async def validate_token(token: str, *, http: httpx.AsyncClient | None = None) -> WkIdentity:
    """One `GET /user`: proves the token works and tells whose it is."""
    client = WaniKaniClient(token.strip(), http=http, retries=1)
    try:
        resp = await client.get("user")
    except WaniKaniError as exc:
        if exc.status in (401, 403):
            raise InvalidTokenError(str(exc)) from exc
        raise
    finally:
        await client.aclose()
    assert resp.data is not None
    return WkIdentity.from_user(resp.data)


@dataclass(slots=True)
class Account:
    key: str
    wk_id: str
    username: str
    level: int | None
    label: str
    owner_tg_id: int | None
    status: str
    status_reason: str | None
    status_at: datetime | None
    token_enc: str
    token_hint: str
    source: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_doc(cls, d: Json) -> Account:
        tok = d.get("token") or {}
        return cls(
            key=str(d["_id"]),
            wk_id=str(d.get("wk_id") or ""),
            username=str(d.get("username") or ""),
            level=d.get("level"),
            label=str(d.get("label") or d["_id"]),
            owner_tg_id=d.get("owner_tg_id"),
            status=str(d.get("status") or ACTIVE),
            status_reason=d.get("status_reason"),
            status_at=d.get("status_at"),
            token_enc=str(tok.get("enc") or ""),
            token_hint=str(tok.get("hint") or ""),
            source=str(d.get("source") or ""),
            created_at=d.get("created_at") or utcnow(),
            updated_at=d.get("updated_at") or utcnow(),
        )

    @property
    def is_active(self) -> bool:
        return self.status == ACTIVE

    @property
    def emoji(self) -> str:
        return STATUS_EMOJI.get(self.status, "•")


class AccountRepo:
    """Accounts collection + `TokenSource` for `SyncEngine`."""

    def __init__(self, db: Db, cipher: TokenCipher | None = None) -> None:
        self.db = db
        self.cipher = cipher

    # ---------------------------------------------------------------- read
    async def get(self, key: str) -> Account | None:
        d = await self.db.accounts.find_one({"_id": key})
        return Account.from_doc(d) if d else None

    async def by_wk_id(self, wk_id: str) -> Account | None:
        d = await self.db.accounts.find_one({"wk_id": wk_id})
        return Account.from_doc(d) if d else None

    async def list(self, *, status: str | None = ACTIVE) -> list[Account]:
        """`status=None` → every account except purged."""
        q: Json = {"status": status} if status else {"status": {"$ne": PURGED}}
        return [
            Account.from_doc(d) async for d in self.db.accounts.find(q, sort=[("created_at", 1)])
        ]

    async def for_owner(self, tg_id: int, *, include_removed: bool = False) -> list[Account]:
        q: Json = {"owner_tg_id": tg_id}
        if not include_removed:
            q["status"] = {"$nin": [REMOVED, PURGED]}
        return [
            Account.from_doc(d) async for d in self.db.accounts.find(q, sort=[("created_at", 1)])
        ]

    async def labels(self) -> dict[str, str]:
        return {
            str(d["_id"]): str(d.get("label") or d["_id"]) async for d in self.db.accounts.find({})
        }

    def token(self, acc: Account) -> str:
        if self.cipher is None:
            raise CipherError("no cipher configured")
        return self.cipher.decrypt(acc.token_enc)

    # --------------------------------------------------------------- write
    def _enc(self, token: str) -> Json:
        if self.cipher is None:
            raise CipherError("no cipher configured")
        return {
            "enc": self.cipher.encrypt(token.strip()),
            "hint": token_hint(token.strip()),
            "key_id": 1,
        }

    async def create(
        self,
        identity: WkIdentity,
        token: str,
        *,
        owner_tg_id: int | None,
        source: str,
        label: str | None = None,
    ) -> Account:
        key = key_for(identity.wk_id)
        clash = await self.get(key)
        if clash is not None and clash.wk_id != identity.wk_id:
            key = key_for(identity.wk_id, 12)
        now = utcnow()
        doc: Json = {
            "_id": key,
            "wk_id": identity.wk_id,
            "username": identity.username,
            "level": identity.level,
            "label": label or identity.username or key,
            "token": self._enc(token),
            "owner_tg_id": owner_tg_id,
            "status": ACTIVE,
            "status_reason": None,
            "status_at": now,
            "source": source,
            "created_at": now,
            "updated_at": now,
            "settings": {},
        }
        await self.db.accounts.insert_one(doc)
        log.info(
            "account %s created (%s, L%s) by %s",
            key,
            identity.username,
            identity.level,
            owner_tg_id,
        )
        return Account.from_doc(doc)

    async def set_token(self, key: str, identity: WkIdentity, token: str) -> Account:
        """Replace the token (rotation / revive); a broken status becomes active again."""
        now = utcnow()
        d = await self.db.accounts.find_one_and_update(
            {"_id": key},
            {
                "$set": {
                    "token": self._enc(token),
                    "username": identity.username,
                    "level": identity.level,
                    "status": ACTIVE,
                    "status_reason": None,
                    "status_at": now,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        assert d is not None, key
        log.info("account %s: token replaced", key)
        return Account.from_doc(d)

    async def set_status(self, key: str, status: str, reason: str | None = None) -> None:
        now = utcnow()
        await self.db.accounts.update_one(
            {"_id": key},
            {
                "$set": {
                    "status": status,
                    "status_reason": reason,
                    "status_at": now,
                    "updated_at": now,
                }
            },
        )
        log.info("account %s → %s%s", key, status, f" ({reason})" if reason else "")

    async def set_label(self, key: str, label: str) -> None:
        await self.db.accounts.update_one(
            {"_id": key}, {"$set": {"label": label.strip(), "updated_at": utcnow()}}
        )

    async def set_owner(self, key: str, owner_tg_id: int | None) -> None:
        await self.db.accounts.update_one(
            {"_id": key}, {"$set": {"owner_tg_id": owner_tg_id, "updated_at": utcnow()}}
        )

    async def remove(self, key: str) -> None:
        await self.set_status(key, REMOVED)

    async def purge(self, key: str) -> dict[str, int]:
        """Delete every per-account document. Only for `removed` accounts; global data untouched."""
        acc = await self.get(key)
        if acc is None or acc.status != REMOVED:
            raise ValueError(
                f"account {key} must exist and be `removed` (is: {acc and acc.status})"
            )
        counts = await delete_account_data(self.db, key)
        await self.db.accounts.update_one(
            {"_id": key}, {"$set": {"status": PURGED, "status_at": utcnow(), "purged_at": utcnow()}}
        )
        log.warning("account %s purged: %s", key, counts)
        return counts

    # ------------------------------------------------- TokenSource protocol
    async def active_tokens(self, keys: list[str] | None = None) -> dict[str, str]:
        out: dict[str, str] = {}
        for acc in await self.list(status=ACTIVE):
            if keys and acc.key not in keys:
                continue
            try:
                out[acc.key] = self.token(acc)
            except CipherError as exc:
                await self.set_status(acc.key, KEY_ERROR, str(exc))
        return out

    async def on_auth_error(self, key: str, message: str) -> None:
        await self.set_status(key, AUTH_ERROR, message)

    async def on_user_seen(self, key: str, item: Json) -> None:
        d = item.get("data") or {}
        await self.db.accounts.update_one(
            {"_id": key},
            {
                "$set": {
                    "username": d.get("username"),
                    "level": d.get("level"),
                    "updated_at": utcnow(),
                }
            },
        )


# ------------------------------------------------------------ data ops
def _account_collections() -> list[tuple[str, bool]]:
    return [(name, res.singleton) for name, res in RESOURCES.items() if res.scope == "account"]


async def delete_account_data(db: Db, key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name, singleton in _account_collections():
        coll = db.current(name)
        if singleton:
            counts[name] = (await coll.delete_one({"_id": key})).deleted_count
        else:
            counts[name] = (await coll.delete_many({"account": key})).deleted_count
    for name in (HISTORY, EVENTS, TG_ROUTES):
        counts[name] = (await db.col(name).delete_many({"account": key})).deleted_count
    counts[SYNC_STATE] = (
        await db.sync_state.delete_many({"_id": {"$regex": f"^{re.escape(key)}:"}})
    ).deleted_count
    return counts


async def rename_key(db: Db, old: str, new: str) -> dict[str, int]:
    """Move every per-account document from key `old` to `new` (idempotent)."""
    counts: dict[str, int] = {}
    for name, singleton in _account_collections():
        coll = db.current(name)
        if singleton:
            doc = await coll.find_one({"_id": old})
            if doc is None:
                counts[name] = 0
                continue
            doc["_id"], doc["account"] = new, new
            await coll.delete_one({"_id": old})
            await coll.replace_one({"_id": new}, doc, upsert=True)
            counts[name] = 1
        else:
            r = await coll.update_many({"account": old}, {"$set": {"account": new}})
            counts[name] = r.modified_count
    for name in (HISTORY, EVENTS, TG_ROUTES):
        r = await db.col(name).update_many({"account": old}, {"$set": {"account": new}})
        counts[name] = r.modified_count
    n = 0
    async for st in db.sync_state.find({"_id": {"$regex": f"^{re.escape(old)}:"}}):
        st["_id"] = f"{new}:{str(st['_id']).split(':', 1)[1]}"
        await db.sync_state.replace_one({"_id": st["_id"]}, st, upsert=True)
        n += 1
    await db.sync_state.delete_many({"_id": {"$regex": f"^{re.escape(old)}:"}})
    counts[SYNC_STATE] = n
    acc = await db.accounts.find_one({"_id": old})
    if acc is not None:  # delete first: `wk_id` is unique
        acc["_id"] = new
        await db.accounts.delete_one({"_id": old})
        await db.accounts.replace_one({"_id": new}, acc, upsert=True)
        counts["accounts"] = 1
    return counts


async def migrate_keys(db: Db, *, dry_run: bool = False) -> list[Json]:
    """Rename legacy keys (`main`, `light`) to `wk_id[:8]`, using the stored `/user` object."""
    out: list[Json] = []
    async for u in db.current("user").find({}):
        old = str(u["_id"])
        wk_id = ((u.get("item") or {}).get("data") or {}).get("id")
        if not wk_id:
            continue
        new = key_for(str(wk_id))
        if new == old:
            continue
        counts = {} if dry_run else await rename_key(db, old, new)
        out.append({"old": old, "new": new, "wk_id": wk_id, **counts})
        log.info("migrate-keys: %s → %s %s", old, new, "(dry-run)" if dry_run else counts)
    return out
