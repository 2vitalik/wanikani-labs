"""Pure UI pieces: texts and keyboards."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId

from wklabs.bot import texts
from wklabs.bot.callbacks import ChatCb
from wklabs.bot.keyboards import (
    kb_account_card,
    kb_accounts,
    kb_chat_card,
    kb_chats,
    kb_pick_chat,
    kb_presets,
    kb_setup_light,
)
from wklabs.lib.accounts import Account
from wklabs.lib.chats import ADMIN, KICKED, MEMBER, Chat, Rights
from wklabs.lib.delivery import Route

NOW = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)


def acc(status: str = "active", owner: int = 42, label: str = "Vitalik") -> Account:
    return Account(
        key="07fff792",
        wk_id="x",
        username="Vitalik",
        level=39,
        label=label,
        owner_tg_id=owner,
        status=status,
        status_reason=None,
        status_at=NOW,
        token_enc="e",
        token_hint="ab12",
        source="bot",
        created_at=NOW,
        updated_at=NOW,
    )


def chat(**kw: Any) -> Chat:
    base = Chat(
        id=-100,
        type="supergroup",
        title="WK",
        is_forum=True,
        status=ADMIN,
        rights=Rights(can_post=True, can_manage_topics=True, can_delete=True),
        member_can_topics=False,
        member_ids=[42],
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


def labels(kb) -> list[str]:
    return [b.text for row in kb.inline_keyboard for b in row]


def test_account_card_and_keyboards():
    forum = chat()
    route = Route(ObjectId(), "07fff792", "reviews", -100, 7, "📝 Vitalik · reviews", True, 42, NOW)
    text = texts.account_card(acc(), [(route, forum)], last_sync=NOW, tz=ZoneInfo("UTC"), now=NOW)
    assert "…ab12" in text and "📝 reviews → WK › 📝 Vitalik · reviews" in text
    text = texts.account_card(acc("auth_error"), [], last_sync=None, tz=ZoneInfo("UTC"), now=NOW)
    assert "token rejected" in text and "no delivery routes" in text
    kb = kb_accounts([acc()], {"07fff792": 12})
    assert kb.inline_keyboard[0][0].text == "🟢 Vitalik · L39 · 12 due"
    assert kb.inline_keyboard[-1][0].text == "➕ Add account"
    assert "⏸ Pause" in labels(kb_account_card(acc())) and "▶️ Resume" not in labels(
        kb_account_card(acc())
    )
    assert "▶️ Resume" in labels(kb_account_card(acc("paused")))


def test_chat_card_text_and_hints():
    route = Route(ObjectId(), "07fff792", "reviews", -100, 7, "📝 Vitalik · reviews", True, 42, NOW)
    text = texts.chat_card(chat(preset="per_category"), [(route, acc())], viewer=42)
    assert "🗂 <b>WK</b> · forum" in text and "topics ✅" in text and "delete ✅" in text
    assert "📝 reviews · Vitalik → 📝 Vitalik · reviews" in text and "(theirs)" not in text
    assert "last preset: topic per category" in text
    text = texts.chat_card(chat(), [(route, acc(owner=7))], viewer=42)
    assert "(theirs)" in text
    assert "Nothing delivered here yet." in texts.chat_card(chat(), [], viewer=42)
    # hints, one line each, with the fixing action
    assert "Manage Topics" in texts.chat_card(chat(status=MEMBER), [], viewer=42)
    assert "Group settings → Topics" in texts.chat_card(chat(is_forum=False), [], viewer=42)
    assert "no longer in this chat" in texts.chat_card(chat(status=KICKED), [], viewer=42)
    assert "can't post" in texts.chat_card(
        chat(status=MEMBER, rights=Rights(can_post=False)), [], viewer=42
    )
    assert "Not checked yet" in texts.chat_card(chat(status="unknown"), [], viewer=42)


def test_chat_keyboards():
    kb = kb_chats(
        [chat(id=42, type="private", title=None), chat(), chat(id=-200, status=KICKED)], {-100: 2}
    )
    assert labels(kb)[0] == "🔒 private · here"
    assert labels(kb)[1] == "🗂 WK · forum · 2 ✓" and labels(kb)[2] == "⚠️ WK · removed me"
    assert labels(kb)[-1] == "➕ Add a chat"
    kb = kb_chat_card(chat(), has_accounts=True, has_routes=True, in_group=False)
    assert labels(kb) == [
        "📬 Deliver here…",
        "🧵 Topics",
        "📨 Send test",
        "🔄 Refresh",
        "🚫 Stop here",
        "« Chats",
    ]
    kb = kb_chat_card(chat(is_forum=False), has_accounts=False, has_routes=False, in_group=True)
    assert labels(kb) == ["📨 Send test", "🔄 Refresh", "🧹 Close"]
    kb = kb_chat_card(chat(status=KICKED), has_accounts=True, has_routes=True, in_group=False)
    assert labels(kb) == ["🔄 Refresh", "🚫 Stop here", "🗑 Forget", "« Chats"]
    assert labels(kb_presets(chat()))[:4] == [
        "✨ topic per category",
        "✨ topic per account",
        "✨ one topic for all",
        "💬 General (no topics)",
    ]
    assert labels(kb_presets(chat(status=MEMBER)))[0] == "📬 Deliver my digests here"
    kb = kb_setup_light(chat(), has_accounts=True, bot_username="wklabs_bot")
    assert labels(kb)[-2:] == ["⚙️ Configure here", "⚙️ In private"]
    assert kb.inline_keyboard[-1][1].url == "https://t.me/wklabs_bot?start=chat_-100"
    kb = kb_setup_light(chat(), has_accounts=False, bot_username="b")
    assert labels(kb) == ["⚙️ Configure here", "⚙️ In private"]
    reply = kb_pick_chat()
    texts_ = [b.text for row in reply.keyboard for b in row]
    assert texts_ == ["📂 Group or forum", "👥 Chat I'm already in", "📢 Channel", "✖️ Cancel"]
    req = reply.keyboard[0][0].request_chat
    assert req and req.bot_administrator_rights and req.bot_administrator_rights.can_manage_topics
    assert reply.keyboard[1][0].request_chat.chat_is_channel is True  # type: ignore[union-attr]


def test_callback_data_fits_telegram_limit():
    longest = ChatCb(chat=-1001234567890123, action="stop_yes", arg="per_category").pack()
    assert len(longest.encode()) <= 64
