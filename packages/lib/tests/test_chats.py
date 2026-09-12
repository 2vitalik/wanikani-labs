"""Chat registry: discovery upserts, inspection, members, topics, migration, hints."""

from dataclasses import replace
from typing import Any

from wklabs.lib.chats import (
    ADMIN,
    GROUP,
    HINT_BASIC_GROUP,
    HINT_CANNOT_POST,
    HINT_FORUM_NOT_ADMIN,
    HINT_GONE,
    HINT_NO_TOPICS_RIGHT,
    HINT_NOT_FORUM,
    HINT_UNKNOWN,
    KICKED,
    MEMBER,
    SUPERGROUP,
    UNKNOWN,
    VIA_ADDED,
    Chat,
    ChatRepo,
    Inspection,
    Rights,
    hints,
)
from wklabs.lib.delivery import RouteRepo


def _insp(**kw: Any) -> Inspection:
    base = Inspection(
        type=SUPERGROUP,
        title="WK",
        is_forum=True,
        status=ADMIN,
        rights=Rights(can_post=True, can_manage_topics=True),
    )
    return replace(base, **kw)


async def test_seen_then_inspection(db):
    chats = ChatRepo(db)
    c = await chats.seen(-100, type=SUPERGROUP, title="WK", member=42, thread=(7, "Chat"))
    assert c.status == UNKNOWN and c.member_ids == [42] and c.topics[7].name == "Chat"
    assert not c.inspected and hints(c) == [HINT_UNKNOWN]
    c = await chats.seen(-100, type=SUPERGROUP, is_forum=True, member=43, thread=(7, None))
    assert c.member_ids == [42, 43] and c.is_forum and c.topics[7].name == "Chat"
    c = await chats.apply_inspection(-100, _insp(), added_by=42)
    assert c.is_admin and c.topics_possible and c.added_by == 42 and c.member_ids == [42, 43]
    assert hints(c) == [] and c.kind == "forum" and c.name == "WK"
    assert c.is_member(42) and not c.is_member(99)
    assert c.topic_by_name("Chat") is not None and c.topic(None) is None


async def test_hints_table():
    def chat(**kw: Any) -> Chat:
        base = Chat(
            id=-1,
            type=SUPERGROUP,
            title="x",
            is_forum=True,
            status=ADMIN,
            rights=Rights(can_post=True, can_manage_topics=True),
            member_can_topics=False,
            member_ids=[],
            topics={},
            preset=None,
            added_by=None,
            checked_at=None,
            last_seen_at=None,
            migrated_to=None,
            greeted_at=None,
            forgotten_at=None,
        )
        return replace(base, **kw)

    assert hints(chat(type="private")) == []
    assert hints(chat(status=KICKED)) == [HINT_GONE]
    assert hints(chat(type=GROUP, is_forum=False, status=MEMBER)) == [HINT_BASIC_GROUP]
    assert hints(chat(is_forum=False, status=MEMBER)) == [HINT_NOT_FORUM]
    assert hints(chat(status=MEMBER)) == [HINT_FORUM_NOT_ADMIN]
    assert hints(chat(rights=Rights(can_manage_topics=False))) == [HINT_NO_TOPICS_RIGHT]
    assert hints(chat(status=MEMBER, rights=Rights(can_post=False))) == [
        HINT_CANNOT_POST,
        HINT_FORUM_NOT_ADMIN,
    ]
    assert not chat(status=MEMBER, rights=Rights(can_post=False)).can_post
    assert chat(type="private").can_post


async def test_topics_registry(db):
    chats = ChatRepo(db)
    await chats.apply_inspection(-100, _insp())
    await chats.remember_topic(-100, 7, "📝 Vitalik · reviews", by_bot=True)
    await chats.remember_topic(-100, 9, "Chat")
    c = await chats.get(-100)
    assert c and c.topics[7].by_bot and c.topics[7].bot_name == "📝 Vitalik · reviews"
    assert not c.topics[9].by_bot
    await chats.remember_topic(-100, 7, "Renamed")  # human rename keeps by_bot + bot_name
    await chats.topic_closed(-100, 9)
    c = await chats.get(-100)
    assert c and c.topics[7].name == "Renamed" and c.topics[7].bot_name == "📝 Vitalik · reviews"
    assert c.topics[9].closed
    await chats.topic_gone(-100, 9)
    c = await chats.get(-100)
    assert c and 9 not in c.topics


async def test_visible_to_status_forget(db):
    chats = ChatRepo(db)
    await chats.apply_inspection(-100, _insp(), added_by=42)
    await chats.add_member(-100, 42, VIA_ADDED)
    await chats.apply_inspection(-200, _insp(title="Other"))
    await chats.add_member(-200, 7, VIA_ADDED)
    mine = await chats.visible_to(42)
    assert [c.id for c in mine] == [42, -100] and mine[0].is_private
    assert [c.id for c in await chats.visible_to(42, admin=True)] == [42, -200, -100]
    await chats.set_status(-100, KICKED)
    c = await chats.get(-100)
    assert c and not c.present and hints(c) == [HINT_GONE]
    await chats.forget(-100)
    assert [c.id for c in await chats.visible_to(42)] == [42]
    await chats.seen(-100, type=SUPERGROUP, member=42)  # bot is back → chat is back
    assert [c.id for c in await chats.visible_to(42)] == [42, -100]
    await chats.set_preset(-100, "per_account")
    await chats.set_greeted(-100)
    c = await chats.get(-100)
    assert c and c.preset == "per_account" and c.greeted_at is not None


async def test_migrate_moves_routes(db):
    chats, routes = ChatRepo(db), RouteRepo(db)
    await chats.apply_inspection(-1, _insp(type=GROUP, is_forum=False, status=MEMBER))
    await chats.add_member(-1, 42, VIA_ADDED)
    await routes.ensure_account_routes("07fff792", -1, created_by=42)
    new = await chats.migrate(-1, -100)
    assert new and new.id == -100 and new.type == SUPERGROUP and new.member_ids == [42]
    assert await routes.migrate_chat(-1, -100) == 2
    old = await chats.get(-1)
    assert old and old.migrated_to == -100 and not old.present
    assert [c.id for c in await chats.visible_to(42)] == [42, -100]
    assert await chats.migrate(-1, -100) is not None  # idempotent
    assert [r.chat_id for r in await routes.for_account("07fff792")] == [-100, -100]


async def test_normalize_legacy(db):
    chats = ChatRepo(db)
    await db.tg_chats.insert_one(
        {
            "_id": -100,
            "type": "supergroup",
            "title": "WK",
            "is_forum": True,
            "layout": "topics",
            "set_up_by": 42,
            "bot_is_admin": True,
            "can_manage_topics": True,
        }
    )
    c = await chats.get(-100)
    assert c and c.member_ids == [42] and c.preset == "per_category" and c.topics_possible
    assert await chats.normalize_legacy() == 1
    d = await db.tg_chats.find_one({"_id": -100})
    assert d and "layout" not in d and d["member_ids"] == [42] and d["status"] == ADMIN
    assert await chats.normalize_legacy() == 0
    assert [x.id for x in await chats.visible_to(42)] == [42, -100]
