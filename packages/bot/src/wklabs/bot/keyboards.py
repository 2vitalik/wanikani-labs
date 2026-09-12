"""Inline keyboards (pure builders)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from wklabs.lib.accounts import ACTIVE, PAUSED, Account
from wklabs.lib.delivery import LAYOUT_SINGLE, LAYOUT_TOPICS, Chat, Route
from wklabs.lib.users import ACTIVE as U_ACTIVE
from wklabs.lib.users import BLOCKED, PENDING, TgUser

from .callbacks import AccCb, AdminCb, NavCb, RouteCb, SetupCb


def _on(flag: bool) -> str:
    return "✅" if flag else "🚫"


def kb_accounts(accounts: list[Account], due: dict[str, int]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for a in accounts:
        extra = f" · {due[a.key]} due" if a.is_active and a.key in due else ""
        b.button(
            text=f"{a.emoji} {a.label} · L{a.level or '?'}{extra}",
            callback_data=AccCb(key=a.key, action="card"),
        )
    b.button(text="➕ Add account", callback_data=NavCb(screen="add"))
    b.adjust(1)
    return b.as_markup()


def kb_welcome() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Add account", callback_data=NavCb(screen="add"))
    b.button(text="ℹ️ How it works", callback_data=NavCb(screen="help"))
    b.adjust(2)
    return b.as_markup()


def kb_cancel() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✖️ Cancel", callback_data=NavCb(screen="cancel"))
    return b.as_markup()


def kb_back_accounts() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="👤 Accounts", callback_data=NavCb(screen="accounts"))
    return b.as_markup()


def kb_account_card(acc: Account) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📬 Delivery", callback_data=AccCb(key=acc.key, action="delivery"))
    b.button(text="✏️ Rename", callback_data=AccCb(key=acc.key, action="rename"))
    b.button(text="🔑 Replace token", callback_data=AccCb(key=acc.key, action="token"))
    if acc.status == ACTIVE:
        b.button(text="⏸ Pause", callback_data=AccCb(key=acc.key, action="pause"))
    elif acc.status == PAUSED:
        b.button(text="▶️ Resume", callback_data=AccCb(key=acc.key, action="resume"))
    b.button(text="🗑 Remove", callback_data=AccCb(key=acc.key, action="remove"))
    b.button(text="« Accounts", callback_data=NavCb(screen="accounts"))
    b.adjust(3, 2, 1)
    return b.as_markup()


def kb_remove_confirm(acc: Account) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🗑 Yes, remove", callback_data=AccCb(key=acc.key, action="remove_yes"))
    b.button(text="« Back", callback_data=AccCb(key=acc.key, action="card"))
    b.adjust(2)
    return b.as_markup()


def kb_delivery(
    acc: Account,
    rows: list[tuple[Route, Chat]],
    subjects: list[tuple[Chat, Route | None]],
    move_to: list[Chat],
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for route, chat in rows:
        b.button(
            text=f"{_on(route.enabled)} {route.category} · {chat.name}",
            callback_data=RouteCb(id=str(route.id)),
        )
    for chat, route in subjects:
        on = bool(route and route.enabled)
        b.button(
            text=f"{_on(on)} subjects · {chat.name}",
            callback_data=AccCb(key=acc.key, action="subj", arg=str(chat.id)),
        )
    for chat in move_to:
        b.button(
            text=f"➡️ Move all to {chat.name}",
            callback_data=AccCb(key=acc.key, action="move", arg=str(chat.id)),
        )
    b.button(text="« Back", callback_data=AccCb(key=acc.key, action="card"))
    b.adjust(1)
    return b.as_markup()


@dataclass(slots=True)
class SetupState:
    accounts: list[str] = field(default_factory=list)
    layout: str = LAYOUT_SINGLE
    subjects: bool = False
    system: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "accounts": list(self.accounts),
            "layout": self.layout,
            "subjects": self.subjects,
            "system": self.system,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> SetupState:
        d = d or {}
        return cls(
            accounts=list(d.get("accounts") or []),
            layout=str(d.get("layout") or LAYOUT_SINGLE),
            subjects=bool(d.get("subjects")),
            system=bool(d.get("system")),
        )


def kb_setup(
    st: SetupState, accounts: list[Account], chat: Chat, *, is_admin: bool
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for a in accounts:
        mark = "☑" if a.key in st.accounts else "☐"
        b.button(text=f"{mark} {a.label}", callback_data=SetupCb(field="acc", value=a.key))
    b.adjust(2)
    if chat.topics_possible:
        row = InlineKeyboardBuilder()
        row.button(
            text=f"{'●' if st.layout == LAYOUT_TOPICS else '○'} topics per account",
            callback_data=SetupCb(field="layout", value=LAYOUT_TOPICS),
        )
        row.button(
            text=f"{'●' if st.layout == LAYOUT_SINGLE else '○'} single stream",
            callback_data=SetupCb(field="layout", value=LAYOUT_SINGLE),
        )
        row.adjust(2)
        b.attach(row)
    opts = InlineKeyboardBuilder()
    opts.button(
        text=f"{'☑' if st.subjects else '☐'} 📚 subjects", callback_data=SetupCb(field="subjects")
    )
    if is_admin:
        opts.button(
            text=f"{'☑' if st.system else '☐'} 🛠 system", callback_data=SetupCb(field="system")
        )
    opts.adjust(2)
    b.attach(opts)
    act = InlineKeyboardBuilder()
    act.button(text="✅ Apply", callback_data=SetupCb(field="apply"))
    act.button(text="✖️ Cancel", callback_data=SetupCb(field="cancel"))
    act.adjust(2)
    b.attach(act)
    return b.as_markup()


def kb_continue_private(bot_username: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Open private chat", url=f"https://t.me/{bot_username}")
    return b.as_markup()


# ------------------------------------------------------------------- admin
def kb_admin_home(users: dict[str, int], accounts: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    pend = f" · pending {users.get(PENDING, 0)}" if users.get(PENDING) else ""
    b.button(text=f"👥 Users {users.get(U_ACTIVE, 0)}{pend}", callback_data=AdminCb(action="users"))
    b.button(text=f"🗂 Accounts {accounts}", callback_data=AdminCb(action="accounts"))
    b.button(text="🔄 Sync now", callback_data=AdminCb(action="sync"))
    b.button(text="🔄 Full sync", callback_data=AdminCb(action="sync_full"))
    b.button(text="📈 Status", callback_data=AdminCb(action="status"))
    b.adjust(2, 2, 1)
    return b.as_markup()


def kb_admin_users(users: list[TgUser]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for u in users:
        icon = {U_ACTIVE: "✅", PENDING: "⏳", BLOCKED: "🚫"}.get(u.status, "•")
        role = " 👑" if u.is_admin else ""
        b.button(
            text=f"{icon} {u.display}{role}", callback_data=AdminCb(action="user", arg=str(u.id))
        )
    b.button(text="« Admin", callback_data=AdminCb(action="home"))
    b.adjust(1)
    return b.as_markup()


def kb_admin_user(u: TgUser) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if u.status != U_ACTIVE:
        b.button(text="✅ Approve", callback_data=AdminCb(action="approve", arg=str(u.id)))
    if u.status != BLOCKED and not u.is_admin:
        b.button(text="🚫 Block", callback_data=AdminCb(action="block", arg=str(u.id)))
    b.button(text="« Users", callback_data=AdminCb(action="users"))
    b.adjust(2, 1)
    return b.as_markup()


def kb_new_user(u: TgUser) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if u.status == PENDING:
        b.button(text="✅ Approve", callback_data=AdminCb(action="approve", arg=str(u.id)))
    b.button(text="🚫 Block", callback_data=AdminCb(action="block", arg=str(u.id)))
    b.adjust(2)
    return b.as_markup()


def kb_admin_accounts(accounts: list[Account]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for a in accounts:
        b.button(
            text=f"{a.emoji} {a.label} · {a.key} · owner {a.owner_tg_id}",
            callback_data=AccCb(key=a.key, action="card"),
        )
    b.button(text="« Admin", callback_data=AdminCb(action="home"))
    b.adjust(1)
    return b.as_markup()


def kb_back_admin() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="« Admin", callback_data=AdminCb(action="home"))
    return b.as_markup()
