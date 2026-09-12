"""Telegram users (roles, access policy) and delivery routes (move, suspend, revive, health)."""

from wklabs.lib.chats import ChatRepo
from wklabs.lib.delivery import (
    ERR_TOPIC_CLOSED,
    PRESET_GENERAL,
    PRESET_ONE_TOPIC,
    PRESET_PER_ACCOUNT,
    PRESET_PER_CATEGORY,
    RouteRepo,
    preset_topic_name,
    topic_title,
)
from wklabs.lib.users import TgUserRepo


async def test_users_policy_and_roles(db):
    repo = TgUserRepo(db, admin_ids=[1], policy="approve")
    admin, new = await repo.ensure(1, first_name="V")
    assert new and admin.is_admin and admin.is_active and admin.display == "V · 1"
    u, new = await repo.ensure(2, username="x")
    assert new and u.status == "pending" and not u.is_admin and u.display == "x @x · 2"
    u, new = await repo.ensure(2)
    assert not new
    await repo.set_status(2, "active", by=1)
    u = await repo.get(2)
    assert u and u.is_active
    assert await repo.admin_ids_all() == [1]
    assert await repo.counts() == {"active": 2, "pending": 0, "blocked": 0}
    assert [x.id for x in await repo.list("active")] == [1, 2]
    u, _ = await TgUserRepo(db, admin_ids=[], policy="open").ensure(3)
    assert u.is_active


def test_presets():
    assert preset_topic_name(PRESET_PER_CATEGORY, "reviews", "Vitalik") == "📝 Vitalik · reviews"
    assert preset_topic_name(PRESET_PER_ACCOUNT, "reviews", "Vitalik") == "Vitalik"
    assert preset_topic_name(PRESET_ONE_TOPIC, "milestones", "Vitalik") == "WaniKani"
    assert preset_topic_name(PRESET_GENERAL, "reviews", "Vitalik") is None
    assert topic_title("subjects", None) == "📚 subjects"


async def test_routes_move_suspend_resume(db):
    chats, routes = ChatRepo(db), RouteRepo(db)
    priv = await chats.ensure_private(42)
    assert priv.is_private and priv.name == "private" and not priv.topics_possible
    r = await routes.ensure_account_routes("07fff792", 42, created_by=42)
    assert [x.category for x in r] == ["reviews", "milestones"] and all(x.enabled for x in r)
    assert len(await routes.for_target("07fff792", "reviews")) == 1
    again = await routes.upsert("07fff792", "reviews", 42, created_by=42)
    assert again.id == r[0].id  # unique (account, category, chat)

    moved = await routes.move_account("07fff792", -100, created_by=42)
    assert [x.chat_id for x in await routes.for_target("07fff792", "reviews")] == [-100]
    assert len(await routes.for_account("07fff792", include_disabled=True)) == 4
    assert await routes.chats_for_account("07fff792") == [-100]
    await routes.set_thread(moved[0].id, 7, topic_title("reviews", "Vitalik"), by=42)
    got = await routes.get(moved[0].id)
    assert got and got.thread_id == 7 and got.thread_title == "📝 Vitalik · reviews"
    assert got.updated_by == 42 and got.icon == "📝" and not got.has_error

    assert await routes.suspend_account("07fff792") == 2
    assert await routes.for_target("07fff792", "reviews") == []
    assert await routes.resume_account("07fff792") == 2
    live = await routes.for_account("07fff792")
    assert len(live) == 2 and {x.chat_id for x in live} == {-100}  # old private ones stay off

    g = await routes.upsert(None, "subjects", -100, created_by=42)
    assert g.account is None and len(await routes.for_target(None, "subjects")) == 1
    assert await routes.disable_for_owner(-100, ["07fff792"]) == 2
    assert len(await routes.for_chat(-100)) == 1  # subjects stays
    assert await routes.disable_chat(-100) == 1


async def test_route_health(db):
    routes = RouteRepo(db)
    r = (await routes.ensure_account_routes("07fff792", -100, created_by=42))[0]
    await routes.set_thread(r.id, 7, "📝 Vitalik · reviews")
    assert await routes.set_error(r.id, ERR_TOPIC_CLOSED) is True
    assert await routes.set_error(r.id, ERR_TOPIC_CLOSED) is False  # same error → no news
    got = await routes.get(r.id)
    assert got and got.has_error and got.error == ERR_TOPIC_CLOSED and got.error_at
    assert await routes.clear_thread(-100, 7) == 1
    got = await routes.get(r.id)
    assert got and got.thread_id is None and got.thread_title == "📝 Vitalik · reviews"
    await routes.clear_error(r.id)
    got = await routes.get(r.id)
    assert got and not got.has_error and got.error is None
    await routes.set_error(r.id, "x")
    await routes.set_thread(r.id, 8, "new")  # new target starts healthy
    got = await routes.get(r.id)
    assert got and not got.has_error
