"""Inline keyboards (pure builders) + the one reply keyboard (chat picker)."""

from __future__ import annotations

from aiogram.types import (
    ChatAdministratorRights,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from wklabs.lib.accounts import ACTIVE, PAUSED, Account
from wklabs.lib.chats import Chat
from wklabs.lib.delivery import (
    ERR_TOPIC_DELETED,
    PRESET_GENERAL,
    PRESET_LABEL,
    PRESETS,
    Route,
)
from wklabs.lib.users import ACTIVE as U_ACTIVE
from wklabs.lib.users import BLOCKED, PENDING, TgUser

from .callbacks import AccCb, AdminCb, ChatCb, NavCb, RouteCb

PICK_CANCEL = "✖️ Cancel"
# request_chat ids: which button was pressed (comes back in `chat_shared.request_id`)
PICK_ADMIN, PICK_MEMBER, PICK_CHANNEL = 1, 2, 3


def _on(flag: bool) -> str:
    return "✅" if flag else "🚫"


def chat_icon(chat: Chat) -> str:
    if not chat.present:
        return "⚠️"
    if chat.is_private:
        return "🔒"
    if chat.is_channel:
        return "📢"
    return "🗂" if chat.is_forum else "👥"


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


def kb_back_chats() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="💬 Chats", callback_data=NavCb(screen="chats"))
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
    b.button(text="➕ Add a chat", callback_data=NavCb(screen="addchat"))
    b.button(text="« Back", callback_data=AccCb(key=acc.key, action="card"))
    b.adjust(1)
    return b.as_markup()


# ------------------------------------------------------------------- chats
def kb_chats(chats: list[Chat], routes: dict[int, int]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for c in chats:
        if c.is_private:
            text = "🔒 private · here"
        elif not c.present:
            text = f"⚠️ {c.name} · removed me"
        else:
            text = f"{chat_icon(c)} {c.name} · {c.kind}"
        if routes.get(c.id):
            text += f" · {routes[c.id]} ✓"
        b.button(text=text, callback_data=ChatCb(chat=c.id, action="card"))
    b.button(text="➕ Add a chat", callback_data=NavCb(screen="addchat"))
    b.adjust(1)
    return b.as_markup()


def kb_chat_card(
    chat: Chat, *, has_accounts: bool, has_routes: bool, in_group: bool
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if chat.is_private:
        b.button(text="📨 Send test", callback_data=ChatCb(chat=chat.id, action="test"))
        b.button(text="« Chats", callback_data=NavCb(screen="chats"))
        b.adjust(1)
        return b.as_markup()
    if chat.present:
        if has_accounts and chat.can_post:
            b.button(text="📬 Deliver here…", callback_data=ChatCb(chat=chat.id, action="deliver"))
        if chat.is_forum:
            b.button(text="🧵 Topics", callback_data=ChatCb(chat=chat.id, action="topics"))
        b.button(text="📨 Send test", callback_data=ChatCb(chat=chat.id, action="test"))
    b.button(text="🔄 Refresh", callback_data=ChatCb(chat=chat.id, action="refresh"))
    if has_routes:
        b.button(text="🚫 Stop here", callback_data=ChatCb(chat=chat.id, action="stop"))
    if not chat.present and not in_group:
        b.button(text="🗑 Forget", callback_data=ChatCb(chat=chat.id, action="forget"))
    if in_group:
        b.button(text="🧹 Close", callback_data=ChatCb(chat=chat.id, action="close"))
    else:
        b.button(text="« Chats", callback_data=NavCb(screen="chats"))
    b.adjust(3, 3, 1) if chat.present else b.adjust(2, 1)
    return b.as_markup()


def kb_presets(chat: Chat, *, back: str = "card") -> InlineKeyboardMarkup:
    """Forum with rights → four presets; anything else → one button (General)."""
    b = InlineKeyboardBuilder()
    if chat.topics_possible:
        for p in PRESETS:
            b.button(
                text=f"✨ {PRESET_LABEL[p]}" if p != PRESET_GENERAL else f"💬 {PRESET_LABEL[p]}",
                callback_data=ChatCb(chat=chat.id, action="preset", arg=p),
            )
        b.adjust(2, 2)
    else:
        b.button(
            text="📬 Deliver my digests here",
            callback_data=ChatCb(chat=chat.id, action="preset", arg=PRESET_GENERAL),
        )
        b.adjust(1)
    tail = InlineKeyboardBuilder()
    tail.button(text="« Back", callback_data=ChatCb(chat=chat.id, action=back))
    b.attach(tail)
    return b.as_markup()


def kb_setup_light(chat: Chat, *, has_accounts: bool, bot_username: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if has_accounts and chat.can_post:
        if chat.topics_possible:
            for p in PRESETS:
                b.button(
                    text=f"✨ {PRESET_LABEL[p]}"
                    if p != PRESET_GENERAL
                    else f"💬 {PRESET_LABEL[p]}",
                    callback_data=ChatCb(chat=chat.id, action="preset", arg=p),
                )
            b.adjust(2, 2)
        else:
            b.button(
                text="📬 Deliver my digests here",
                callback_data=ChatCb(chat=chat.id, action="preset", arg=PRESET_GENERAL),
            )
            b.adjust(1)
    tail = InlineKeyboardBuilder()
    tail.button(text="⚙️ Configure here", callback_data=ChatCb(chat=chat.id, action="card"))
    tail.button(text="⚙️ In private", url=deep_link(bot_username, chat.id))
    tail.adjust(2)
    b.attach(tail)
    return b.as_markup()


def deep_link(bot_username: str, chat_id: int) -> str:
    return f"https://t.me/{bot_username}?start=chat_{chat_id}"


def kb_stop_confirm(chat: Chat) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🚫 Yes, stop", callback_data=ChatCb(chat=chat.id, action="stop_yes"))
    b.button(text="« Back", callback_data=ChatCb(chat=chat.id, action="card"))
    b.adjust(2)
    return b.as_markup()


def kb_topics(chat: Chat) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="« Chat", callback_data=ChatCb(chat=chat.id, action="card"))
    return b.as_markup()


def kb_greet(chat: Chat) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📬 Deliver here…", callback_data=ChatCb(chat=chat.id, action="deliver"))
    b.button(text="Later", callback_data=ChatCb(chat=chat.id, action="later"))
    b.adjust(2)
    return b.as_markup()


def kb_route_error(route: Route) -> InlineKeyboardMarkup | None:
    if route.error != ERR_TOPIC_DELETED:
        return None
    b = InlineKeyboardBuilder()
    b.button(text="✨ Recreate topic", callback_data=RouteCb(id=str(route.id), action="recreate"))
    b.button(text="💬 Chats", callback_data=NavCb(screen="chats"))
    b.adjust(2)
    return b.as_markup()


def kb_pick_chat() -> ReplyKeyboardMarkup:
    """The only reply keyboard: `request_chat` lives nowhere else (Bot API)."""
    admin = ChatAdministratorRights(
        is_anonymous=False,
        can_manage_chat=True,
        can_delete_messages=False,
        can_manage_video_chats=False,
        can_restrict_members=False,
        can_promote_members=False,
        can_change_info=False,
        can_invite_users=False,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
        can_manage_topics=True,
    )
    channel = admin.model_copy(update={"can_manage_topics": False, "can_post_messages": True})
    rows = [
        [
            KeyboardButton(
                text="📂 Group or forum",
                request_chat=KeyboardButtonRequestChat(
                    request_id=PICK_ADMIN,
                    chat_is_channel=False,
                    bot_administrator_rights=admin,
                    request_title=True,
                ),
            ),
            KeyboardButton(
                text="👥 Chat I'm already in",
                request_chat=KeyboardButtonRequestChat(
                    request_id=PICK_MEMBER,
                    chat_is_channel=False,
                    bot_is_member=True,
                    request_title=True,
                ),
            ),
        ],
        [
            KeyboardButton(
                text="📢 Channel",
                request_chat=KeyboardButtonRequestChat(
                    request_id=PICK_CHANNEL,
                    chat_is_channel=True,
                    bot_administrator_rights=channel,
                    request_title=True,
                ),
            ),
            KeyboardButton(text=PICK_CANCEL),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


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
