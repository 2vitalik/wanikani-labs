"""Pure UI pieces: texts and keyboards."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from bson import ObjectId

from wklabs.bot import texts
from wklabs.bot.keyboards import SetupState, kb_account_card, kb_accounts, kb_setup
from wklabs.lib.accounts import Account
from wklabs.lib.delivery import Chat, Route

NOW = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)


def acc(status: str = "active") -> Account:
    return Account(
        key="07fff792",
        wk_id="x",
        username="Vitalik",
        level=39,
        label="Vitalik",
        owner_tg_id=42,
        status=status,
        status_reason=None,
        status_at=NOW,
        token_enc="e",
        token_hint="ab12",
        source="bot",
        created_at=NOW,
        updated_at=NOW,
    )


def test_account_card_and_keyboards():
    chat = Chat(-100, "supergroup", "WK", True, "topics", 42, True, True)
    route = Route(ObjectId(), "07fff792", "reviews", -100, 7, "📝 Vitalik · reviews", True, 42, NOW)
    text = texts.account_card(acc(), [(route, chat)], last_sync=NOW, tz=ZoneInfo("UTC"), now=NOW)
    assert "…ab12" in text and "📝 reviews → WK › 📝 Vitalik · reviews" in text
    text = texts.account_card(acc("auth_error"), [], last_sync=None, tz=ZoneInfo("UTC"), now=NOW)
    assert "token rejected" in text and "no delivery routes" in text
    kb = kb_accounts([acc()], {"07fff792": 12})
    assert kb.inline_keyboard[0][0].text == "🟢 Vitalik · L39 · 12 due"
    assert kb.inline_keyboard[-1][0].text == "➕ Add account"
    labels = [b.text for row in kb_account_card(acc()).inline_keyboard for b in row]
    assert "⏸ Pause" in labels and "▶️ Resume" not in labels
    labels = [b.text for row in kb_account_card(acc("paused")).inline_keyboard for b in row]
    assert "▶️ Resume" in labels


def test_setup_state_and_keyboard():
    st = SetupState(accounts=["07fff792"], layout="topics", subjects=True)
    assert SetupState.from_dict(st.to_dict()) == st
    forum = Chat(-100, "supergroup", "WK", True, "topics", 42, True, True)
    group = Chat(-200, "group", "G", False, "single", 42, False, False)
    labels = [
        b.text for row in kb_setup(st, [acc()], forum, is_admin=True).inline_keyboard for b in row
    ]
    assert "☑ Vitalik" in labels and "● topics per account" in labels and "☐ 🛠 system" in labels
    labels = [
        b.text for row in kb_setup(st, [acc()], group, is_admin=False).inline_keyboard for b in row
    ]
    assert not any("topics per account" in x for x in labels) and not any(
        "system" in x for x in labels
    )
    assert "Manage Topics" not in texts.setup_screen(group, st, mine=1)
    assert "one topic per account" in texts.setup_screen(forum, st, mine=1)
