"""AccountRepo: keys from wk_id, encrypted tokens, statuses, purge, legacy key migration."""

import pytest

from wklabs.lib.accounts import (
    AccountRepo,
    WkIdentity,
    key_for,
    looks_like_token,
    migrate_keys,
)
from wklabs.lib.crypto import TokenCipher, generate_key

WK1 = "07fff792-eea6-4699-9053-46f67ef92656"
WK2 = "27f9b9f5-c9ba-4412-93f4-12a776853982"


def ident(wk_id: str, username: str = "Vitalik", level: int = 39) -> WkIdentity:
    return WkIdentity(wk_id, username, level, "lifetime", 60)


def test_helpers():
    assert key_for(WK1) == "07fff792" and key_for(WK1, 12) == "07fff792eea6"
    assert looks_like_token(f"  {WK1.upper()} ") and not looks_like_token("07fff792")
    assert WkIdentity.from_user(
        {
            "data": {
                "id": WK2,
                "username": "2vitalik",
                "level": 7,
                "subscription": {"type": "lifetime"},
            }
        }
    ) == WkIdentity(WK2, "2vitalik", 7, "lifetime", None)


async def test_create_and_lookup(db):
    repo = AccountRepo(db, TokenCipher(generate_key()))
    acc = await repo.create(ident(WK1), "tok-1234", owner_tg_id=42, source="test")
    assert acc.key == "07fff792" and acc.label == "Vitalik" and acc.token_hint == "1234"
    assert acc.is_active and acc.emoji == "🟢"
    assert repo.token(acc) == "tok-1234" and acc.token_enc != "tok-1234"
    got = await repo.by_wk_id(WK1)
    assert got and got.key == "07fff792"
    assert [a.key for a in await repo.for_owner(42)] == ["07fff792"]
    assert await repo.for_owner(43) == []
    assert await repo.labels() == {"07fff792": "Vitalik"}
    assert await repo.active_tokens() == {"07fff792": "tok-1234"}
    assert await repo.active_tokens(["nope"]) == {}
    await repo.set_label("07fff792", " Vit ")
    got = await repo.get("07fff792")
    assert got and got.label == "Vit"


async def test_key_collision_uses_longer_key(db):
    repo = AccountRepo(db, TokenCipher(generate_key()))
    await repo.create(ident(WK1), "a", owner_tg_id=1, source="t")
    other = WK1[:8] + "-ffff-4699-9053-000000000000"
    acc2 = await repo.create(ident(other, "Other"), "b", owner_tg_id=1, source="t")
    assert acc2.key == "07fff792ffff"


async def test_status_flow_and_key_error(db):
    repo = AccountRepo(db, TokenCipher(generate_key()))
    acc = await repo.create(ident(WK1), "tok1", owner_tg_id=1, source="t")
    await repo.on_auth_error(acc.key, "HTTP 401")
    a = await repo.get(acc.key)
    assert a and a.status == "auth_error" and a.status_reason == "HTTP 401"
    assert await repo.active_tokens() == {}  # not polled anymore
    a = await repo.set_token(acc.key, ident(WK1, level=40), "tok2")
    assert a.status == "active" and a.level == 40 and a.token_hint == "tok2"
    await repo.on_user_seen(acc.key, {"data": {"username": "Vitalik", "level": 41}})
    a = await repo.get(acc.key)
    assert a and a.level == 41
    # a different secret key → key_error, not a crash
    repo2 = AccountRepo(db, TokenCipher(generate_key()))
    assert await repo2.active_tokens() == {}
    a = await repo2.get(acc.key)
    assert a and a.status == "key_error"


async def test_purge_only_removed_and_keeps_global(db):
    repo = AccountRepo(db, TokenCipher(generate_key()))
    acc = await repo.create(ident(WK1), "tok", owner_tg_id=1, source="t")
    k = acc.key
    await db.history.insert_many(
        [
            {"resource": "assignments", "account": k, "resource_id": 1, "data_updated_at": "x"},
            {"resource": "subjects", "account": None, "resource_id": 1, "data_updated_at": "x"},
        ]
    )
    await db.current("assignments").insert_one({"_id": 1, "account": k})
    await db.current("user").insert_one({"_id": k, "account": k})
    await db.sync_state.insert_one({"_id": f"{k}:assignments"})
    await db.tg_routes.insert_one({"account": k, "category": "reviews", "chat_id": 1})
    with pytest.raises(ValueError):
        await repo.purge(k)
    await repo.remove(k)
    assert await repo.for_owner(1) == [] and len(await repo.for_owner(1, include_removed=True)) == 1
    counts = await repo.purge(k)
    assert counts["history"] == 1 and counts["assignments"] == 1 and counts["user"] == 1
    assert counts["sync_state"] == 1 and counts["tg_routes"] == 1
    assert await db.history.count_documents({}) == 1  # global version kept
    a = await repo.get(k)
    assert a and a.status == "purged"
    assert await repo.list(status=None) == []


async def test_migrate_legacy_keys(db):
    await db.current("user").insert_one(
        {"_id": "main", "account": "main", "item": {"data": {"id": WK1, "username": "Vitalik"}}}
    )
    await db.current("summary").insert_one({"_id": "main", "account": "main"})
    await db.current("assignments").insert_many(
        [
            {"_id": 1, "account": "main", "subject_id": 1},
            {"_id": 2, "account": "main", "subject_id": 2},
            {"_id": 3, "account": "x", "subject_id": 1},
        ]
    )
    await db.history.insert_one(
        {"resource": "assignments", "account": "main", "resource_id": 1, "data_updated_at": "x"}
    )
    await db.events.insert_one({"account": "main", "kind": "reviewed", "history_id": 1})
    await db.sync_state.insert_one({"_id": "main:assignments", "updated_after": "u"})
    await db.accounts.insert_one({"_id": "main", "wk_id": WK1, "status": "active"})

    dry = await migrate_keys(db, dry_run=True)
    assert [(r["old"], r["new"]) for r in dry] == [("main", "07fff792")]
    assert await db.sync_state.find_one({"_id": "main:assignments"})  # dry-run touched nothing

    res = await migrate_keys(db)
    r = res[0]
    assert r["assignments"] == 2 and r["history"] == 1 and r["events"] == 1
    assert r["sync_state"] == 1 and r["accounts"] == 1 and r["user"] == 1 and r["summary"] == 1
    assert await db.current("assignments").count_documents({"account": "07fff792"}) == 2
    u = await db.current("user").find_one({"_id": "07fff792"})
    assert u and u["account"] == "07fff792"
    assert await db.current("user").find_one({"_id": "main"}) is None
    st = await db.sync_state.find_one({"_id": "07fff792:assignments"})
    assert st and st["updated_after"] == "u"
    assert await db.sync_state.find_one({"_id": "main:assignments"}) is None
    assert await db.accounts.find_one({"_id": "07fff792"})
    assert await migrate_keys(db) == []  # idempotent
