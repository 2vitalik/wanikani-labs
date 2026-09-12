"""Settings registry: applicability, layers, cycling; route subscribe/move/add."""

from datetime import UTC, datetime

from bson import ObjectId

from wklabs.lib.delivery import Route, RouteRepo
from wklabs.lib.route_settings import (
    ITEMS,
    SILENT,
    effective,
    for_category,
    help_line,
)

NOW = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)


def route(category: str = "reviews", settings: dict | None = None) -> Route:
    return Route(
        ObjectId(), "07fff792", category, -100, None, None, True, 42, NOW, settings=settings or {}
    )


def test_registry_and_effective():
    assert [s.key for s in for_category("reviews")] == ["silent", "items"]
    assert [s.key for s in for_category("milestones")] == ["silent"]
    assert effective(route()) == {"silent": False, "items": "all"}
    assert effective(route("milestones")) == {"silent": False}
    r = route(settings={"items": "wrong", "silent": "yes", "bogus": 1})  # invalid types ignored
    assert effective(r) == {"silent": False, "items": "wrong"}
    assert effective(route(), {"silent": True}) == {"silent": True, "items": "all"}
    assert effective(route(settings={"silent": False}), {"silent": True})["silent"] is False
    assert SILENT.next_value(False) is True and SILENT.display(True) == "🔕 Silent: on"
    assert ITEMS.next_value("all") == "wrong" and ITEMS.next_value("none") == "all"
    assert ITEMS.next_value("weird") == "all" and ITEMS.display("wrong") == "📄 Items: wrong only"
    assert "silent" in help_line("milestones") and "items" not in help_line("milestones")


async def test_subscribe_move_add(db):
    routes = RouteRepo(db)
    r = await routes.subscribe("subjects", -100, 42)
    assert r.enabled and r.subscribers == [42] and r.account is None
    r = await routes.subscribe("subjects", -100, 7)
    assert r.subscribers == [42, 7] and len(await routes.for_chat(-100)) == 1  # one route, no dup
    r = await routes.unsubscribe("subjects", -100, 42)
    assert r and r.enabled and r.subscribers == [7]
    r = await routes.unsubscribe("subjects", -100, 7)
    assert r and not r.enabled and r.subscribers == []
    assert await routes.unsubscribe("subjects", -999, 7) is None

    a = await routes.add_target("07fff792", "reviews", -100, 7, "📝 V · reviews", by=42)
    assert a.thread_id == 7 and a.enabled
    moved = await routes.move_route(a, -100, None, None, by=42)
    assert moved.id == a.id and moved.thread_id is None  # same chat → retarget in place
    moved = await routes.move_route(moved, -200, 9, "T", by=42)
    assert moved.id != a.id and moved.chat_id == -200 and moved.thread_id == 9
    old = await routes.get(a.id)
    assert old and not old.enabled
    also = await routes.add_target("07fff792", "reviews", 42, None, None, by=42)
    assert {x.chat_id for x in await routes.for_target("07fff792", "reviews")} == {-200, 42}
    await routes.set_setting(also.id, "silent", True, by=42)
    got = await routes.get(also.id)
    assert got and got.settings == {"silent": True} and got.updated_by == 42
