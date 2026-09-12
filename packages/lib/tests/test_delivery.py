"""Telegram users (roles, access policy) and delivery routes (move, suspend, revive)."""

from wklabs.lib.delivery import ChatRepo, RouteRepo, topic_title
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


async def test_routes_move_suspend_resume(db):
    chats, routes = ChatRepo(db), RouteRepo(db)
    priv = await chats.ensure_private(42)
    assert priv.is_private and priv.name == "private" and not priv.topics_possible
    r = await routes.ensure_account_routes("07fff792", 42, created_by=42)
    assert [x.category for x in r] == ["reviews", "milestones"] and all(x.enabled for x in r)
    assert len(await routes.for_target("07fff792", "reviews")) == 1
    again = await routes.upsert("07fff792", "reviews", 42, created_by=42)
    assert again.id == r[0].id  # unique (account, category, chat)

    forum = await chats.upsert(
        -100,
        type="supergroup",
        title="WK",
        is_forum=True,
        layout="topics",
        set_up_by=42,
        bot_is_admin=True,
        can_manage_topics=True,
    )
    assert forum.topics_possible and forum.name == "WK"
    assert [c.id for c in await chats.for_user(42)] == [42, -100]
    moved = await routes.move_account("07fff792", -100, created_by=42)
    assert [x.chat_id for x in await routes.for_target("07fff792", "reviews")] == [-100]
    assert len(await routes.for_account("07fff792", include_disabled=True)) == 4
    assert await routes.chats_for_account("07fff792") == [-100]
    await routes.set_thread(moved[0].id, 7, topic_title("reviews", "Vitalik"))
    got = await routes.get(moved[0].id)
    assert got and got.thread_id == 7 and got.thread_title == "📝 Vitalik · reviews"

    assert await routes.suspend_account("07fff792") == 2
    assert await routes.for_target("07fff792", "reviews") == []
    assert await routes.resume_account("07fff792") == 2
    live = await routes.for_account("07fff792")
    assert len(live) == 2 and {x.chat_id for x in live} == {-100}  # old private ones stay off

    g = await routes.upsert(None, "subjects", -100, created_by=42)
    assert g.account is None and len(await routes.for_target(None, "subjects")) == 1
    assert await routes.disable_chat(-100) == 3
