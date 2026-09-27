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
from bson import ObjectId

from wklabs.lib.accounts import ACTIVE, PAUSED, Account
from wklabs.lib.chats import Chat, Topic
from wklabs.lib.delivery import (
    ADDABLE_KINDS,
    ERR_TOPIC_DELETED,
    KINDS,
    PRESET_GENERAL,
    PRESET_LABEL,
    PRESETS,
    Route,
)
from wklabs.lib.notify_settings import BY_KEY, VIEW_KEYS, Setting
from wklabs.lib.progress import LEVELS_CHOICES, PROGRESS_OPTIONS, option_label
from wklabs.lib.users import ACTIVE as U_ACTIVE
from wklabs.lib.users import BLOCKED, PENDING, TgUser

from .callbacks import (
    AccCb,
    AdminCb,
    ChatCb,
    NavCb,
    ProgressCb,
    RouteCb,
    SessionCb,
    TargetCb,
    TopicCb,
    ViewCb,
)
from .texts import chat_icon

PICK_CANCEL = "✖️ Cancel"
# request_chat ids: which button was pressed (comes back in `chat_shared.request_id`)
PICK_ADMIN, PICK_MEMBER, PICK_CHANNEL = 1, 2, 3


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


def kb_back_chats() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="💬 Chats", callback_data=NavCb(screen="chats"))
    return b.as_markup()


def kb_setup_private() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Add a chat", callback_data=NavCb(screen="addchat"))
    b.button(text="💬 Chats", callback_data=NavCb(screen="chats"))
    b.adjust(2)
    return b.as_markup()


def kb_account_card(acc: Account) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📬 Notifications", callback_data=AccCb(key=acc.key, action="notif"))
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


def route_button_text(route: Route, chat: Chat) -> str:
    where = chat.name + (
        f" › {route.thread_title}" if route.thread_id and route.thread_title else ""
    )
    marks = " 🔕" if route.settings.get("silent") else ""
    marks += " ⚠️" if route.has_error else ""
    return f"{_on(route.enabled)} {where}{marks}"


def kb_notifications(
    acc: Account, kinds: list[str], subjects: list[tuple[Chat, Route | None, bool]]
) -> InlineKeyboardMarkup:
    """Account hub: one button per kind (T34 §4.1), subjects per chat, add / move all."""
    b = InlineKeyboardBuilder()
    for kind in kinds:
        k = KINDS[kind]
        b.button(
            text=f"{k.icon} {k.title}", callback_data=AccCb(key=acc.key, action="kind", arg=kind)
        )
    b.adjust(2)
    rest = InlineKeyboardBuilder()
    for chat, route, mine in subjects:
        on = bool(route and route.enabled)
        others = len([x for x in (route.subscribers if route else []) if x != acc.owner_tg_id])
        who = (" · you" if mine else "") + (f" + {others}" if others else "")
        rest.button(
            text=f"{_on(on)} 📚 subjects · {chat.name}{who}",
            callback_data=AccCb(key=acc.key, action="subj", arg=str(chat.id)),
        )
    rest.button(text="➕ Add…", callback_data=AccCb(key=acc.key, action="addkind"))
    rest.button(text="➡️ Move all to…", callback_data=AccCb(key=acc.key, action="moveall"))
    rest.button(text="« Back", callback_data=AccCb(key=acc.key, action="card"))
    rest.adjust(1, 1, 1)
    b.attach(rest)
    return b.as_markup()


def kb_add_kind(acc: Account) -> InlineKeyboardMarkup:
    """`➕ Add…`: what should I post? One line per kind with its blurb (T34 §4.2)."""
    b = InlineKeyboardBuilder()
    for kind in ADDABLE_KINDS:
        k = KINDS[kind]
        b.button(
            text=f"{k.icon} {k.title} — {k.blurb}",
            callback_data=AccCb(key=acc.key, action="add", arg=kind),
        )
    b.button(text="« Back", callback_data=AccCb(key=acc.key, action="notif"))
    b.adjust(1)
    return b.as_markup()


def kb_kind(acc: Account, kind: str, rows: list[tuple[Route, Chat]]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for route, chat in rows:
        b.button(
            text=route_button_text(route, chat),
            callback_data=RouteCb(id=str(route.id), action="card"),
        )
    b.button(text="➕ Also post to…", callback_data=AccCb(key=acc.key, action="add", arg=kind))
    b.button(text="« Notifications", callback_data=AccCb(key=acc.key, action="notif"))
    b.adjust(1)
    return b.as_markup()


def kb_route(
    route: Route,
    settings: list[tuple[Setting, object]],
    *,
    can_toggle: bool,
    can_settings: bool,
    can_target: bool,
    back_text: str,
    back_cb: AccCb | ChatCb,
    has_more: bool = False,
) -> InlineKeyboardMarkup:
    """Card (L1): on/off + level-1 settings; `⚙️ More…` opens level 2 (T34 §4.3)."""
    b = InlineKeyboardBuilder()
    rid = str(route.id)
    if can_toggle:
        b.button(
            text="✅ on" if route.enabled else "🚫 off",
            callback_data=RouteCb(id=rid, action="toggle"),
        )
    if can_settings:
        for setting, value in settings:
            b.button(
                text=setting.display(value),
                callback_data=RouteCb(id=rid, action="set", arg=setting.key),
            )
    b.adjust(3)
    act = InlineKeyboardBuilder()
    if can_settings and has_more:
        act.button(text="⚙️ More…", callback_data=RouteCb(id=rid, action="more"))
    if can_target:
        act.button(text="📍 Change target", callback_data=RouteCb(id=rid, action="target"))
    if route.kind == "session":
        act.button(text="📨 Preview", callback_data=RouteCb(id=rid, action="preview"))
    else:
        act.button(text="📨 Send test", callback_data=RouteCb(id=rid, action="test"))
    if route.error == ERR_TOPIC_DELETED and route.thread_id is None:
        act.button(text="✨ Recreate topic", callback_data=RouteCb(id=rid, action="recreate"))
    act.adjust(2)
    b.attach(act)
    back = InlineKeyboardBuilder()
    back.button(text=back_text, callback_data=back_cb)
    b.attach(back)
    return b.as_markup()


def kb_route_more(route: Route, settings: list[tuple[Setting, object]]) -> InlineKeyboardMarkup:
    """`⚙️ More…` (L2): blocks and map options as cycling buttons, reset, back to the card."""
    b = InlineKeyboardBuilder()
    rid = str(route.id)
    for setting, value in settings:
        b.button(
            text=setting.display(value),
            callback_data=RouteCb(id=rid, action="set2", arg=setting.key),
        )
    b.adjust(2)
    tail = InlineKeyboardBuilder()
    tail.button(text="↩️ Reset to defaults", callback_data=RouteCb(id=rid, action="reset"))
    tail.button(text="« Card", callback_data=RouteCb(id=rid, action="card"))
    tail.adjust(2)
    b.attach(tail)
    return b.as_markup()


def view_button_text(key: str, value: object) -> str:
    if key == "group":
        return "🗂 grouped" if value else "🗂 flat"
    icon = "📄" if key == "items" else "↕️"
    return f"{icon} {BY_KEY[key].shown(value)}"


def kb_session(
    session_id: ObjectId,
    *,
    live: bool,
    route_id: ObjectId | None = None,
    opts: dict[str, object] | None = None,
) -> InlineKeyboardMarkup:
    """Under a session message: ⏹ while it is open, 🗺 always (T34 §4.7); with a route — the
    view row: items · sort · group cycle the route's settings and re-render in place (T40)."""
    b = InlineKeyboardBuilder()
    sid = str(session_id)
    if live:
        b.button(text="⏹ End now", callback_data=SessionCb(id=sid, action="end"))
    b.button(text="🗺 Progress", callback_data=SessionCb(id=sid, action="map"))
    b.adjust(2)
    if route_id is not None and opts is not None:
        view = InlineKeyboardBuilder()
        for key in VIEW_KEYS:
            if key in opts:
                view.button(
                    text=view_button_text(key, opts[key]),
                    callback_data=ViewCb(s=sid, r=str(route_id), opt=key),
                )
        view.adjust(3)
        b.attach(view)
    return b.as_markup()


def kb_progress(
    key: str, opts: dict[str, str], *, accounts: list[Account], in_group: bool
) -> InlineKeyboardMarkup:
    """`/progress`: levels as one radio row (any range in one tap), the rest cycle; the message
    re-renders in place."""
    b = InlineKeyboardBuilder()
    for value, label in LEVELS_CHOICES:
        mark = "• " if opts["levels"] == value else ""
        b.button(text=f"{mark}{label}", callback_data=ProgressCb(key=key, opt="levels", arg=value))
    for opt in ("sort", "group", "filter", "style", "diff"):
        word = "Δ" if opt == "diff" else opt
        b.button(
            text=f"{word}: {option_label(opt, opts[opt])}",
            callback_data=ProgressCb(key=key, opt=opt),
        )
    b.button(text="🔄", callback_data=ProgressCb(key=key, opt="refresh"))
    b.adjust(len(LEVELS_CHOICES), 3, 3)
    tail = InlineKeyboardBuilder()
    for a in accounts:
        if a.key != key:
            tail.button(text=f"👤 {a.label}", callback_data=ProgressCb(key=a.key, opt="acc"))
    if in_group:
        tail.button(text="🧹 Close", callback_data=ProgressCb(key=key, opt="close"))
    tail.adjust(3)
    b.attach(tail)
    assert PROGRESS_OPTIONS
    return b.as_markup()


def kb_pick_chat_target(
    chats: list[Chat], current: int | None, back_cb: AccCb | RouteCb
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for c in chats:
        mark = " ← current" if c.id == current else ""
        b.button(text=f"{chat_icon(c)} {c.name}{mark}", callback_data=TargetCb(chat=c.id))
    b.button(text="➕ Add a chat", callback_data=NavCb(screen="addchat"))
    b.button(text="« Back", callback_data=back_cb)
    b.adjust(1)
    return b.as_markup()


def kb_pick_topic(chat: Chat, auto_name: str | None, current: int | None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if auto_name and chat.topics_possible:
        b.button(text=f"✨ Auto: {auto_name}", callback_data=TargetCb(chat=chat.id, thread="a"))
    b.button(
        text="💬 General" + (" ← current" if current is None else ""),
        callback_data=TargetCb(chat=chat.id, thread="g"),
    )
    for t in sorted(chat.topics.values(), key=lambda x: x.thread_id):
        if t.closed:
            continue
        mark = " ← current" if t.thread_id == current else ""
        b.button(
            text=f"{t.name}{mark}", callback_data=TargetCb(chat=chat.id, thread=str(t.thread_id))
        )
    if chat.topics_possible:
        b.button(text="➕ New topic…", callback_data=TargetCb(chat=chat.id, thread="n"))
    b.button(text="« Chats", callback_data=TargetCb(chat=0))
    b.adjust(1)
    return b.as_markup()


def kb_routes_here(chat: Chat, rows: list[tuple[Route, Account | None]]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for route, acc in rows:
        who = f" · {acc.label}" if acc else ""
        where = f" → {route.thread_title}" if route.thread_id and route.thread_title else ""
        b.button(
            text=f"{route.icon} {route.title}{who}{where}",
            callback_data=RouteCb(id=str(route.id), action="card"),
        )
    b.button(text="« Chat", callback_data=ChatCb(chat=chat.id, action="card"))
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
    chat: Chat,
    *,
    has_accounts: bool,
    has_routes: bool,
    in_group: bool,
    any_routes: bool = False,
    subjects_on: bool = False,
    system_on: bool = False,
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if chat.is_private:
        b.button(text="📨 Send test", callback_data=ChatCb(chat=chat.id, action="test"))
        b.button(text="« Chats", callback_data=NavCb(screen="chats"))
        b.adjust(1)
        return b.as_markup()
    rows: list[int] = []
    if chat.present:
        n = 0
        if has_accounts and chat.can_post:
            b.button(text="📬 Deliver here…", callback_data=ChatCb(chat=chat.id, action="deliver"))
            n += 1
        if chat.is_forum:
            b.button(text="🧵 Topics", callback_data=ChatCb(chat=chat.id, action="topics"))
            n += 1
        b.button(text="📨 Send test", callback_data=ChatCb(chat=chat.id, action="test"))
        rows.append(n + 1)
        n = 0
        if any_routes:
            b.button(text="🧭 Routes here", callback_data=ChatCb(chat=chat.id, action="routes"))
            n += 1
        if chat.can_post:
            b.button(
                text=f"📚 Subjects: {'on' if subjects_on else 'off'}",
                callback_data=ChatCb(chat=chat.id, action="subj"),
            )
            n += 1
        if is_admin and chat.can_post:
            b.button(
                text=f"🛠 System: {'on' if system_on else 'off'}",
                callback_data=ChatCb(chat=chat.id, action="sys"),
            )
            n += 1
        if n:
            rows.append(n)
    n = 1
    b.button(text="🔄 Refresh", callback_data=ChatCb(chat=chat.id, action="refresh"))
    if has_routes:
        b.button(text="🚫 Stop here", callback_data=ChatCb(chat=chat.id, action="stop"))
        n += 1
    if not chat.present and not in_group:
        b.button(text="🗑 Forget", callback_data=ChatCb(chat=chat.id, action="forget"))
        n += 1
    rows.append(n)
    if in_group:
        b.button(text="🧹 Close", callback_data=ChatCb(chat=chat.id, action="close"))
    else:
        b.button(text="« Chats", callback_data=NavCb(screen="chats"))
    rows.append(1)
    b.adjust(*rows)
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


def kb_topics(chat: Chat, *, renamable: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if chat.topics_possible:
        b.button(text="➕ New topic", callback_data=ChatCb(chat=chat.id, action="newtopic"))
        if renamable:
            b.button(text="✏️ Rename…", callback_data=ChatCb(chat=chat.id, action="rename"))
    b.button(text="« Chat", callback_data=ChatCb(chat=chat.id, action="card"))
    b.adjust(2, 1)
    return b.as_markup()


def kb_rename_pick(chat: Chat, topics: list[Topic]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in topics:
        b.button(text=t.name, callback_data=TopicCb(chat=chat.id, thread=t.thread_id))
    b.button(text="« Topics", callback_data=ChatCb(chat=chat.id, action="topics"))
    b.adjust(1)
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
    # Telegram: bot rights must be a subset of the *user's* required rights, which therefore
    # must be sent too (else USER_RIGHTS_MISSING); adding an admin needs can_promote_members
    admin_user = admin.model_copy(update={"can_promote_members": True})
    channel_user = channel.model_copy(update={"can_promote_members": True})
    rows = [
        [
            KeyboardButton(
                text="📂 Group or forum",
                request_chat=KeyboardButtonRequestChat(
                    request_id=PICK_ADMIN,
                    chat_is_channel=False,
                    user_administrator_rights=admin_user,
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
                    user_administrator_rights=channel_user,
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
