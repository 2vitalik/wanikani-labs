"""Bot texts (Telegram HTML, EN). Pure functions — no I/O."""

from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from wklabs.lib.accounts import AUTH_ERROR, KEY_ERROR, Account, WkIdentity
from wklabs.lib.chats import (
    HINT_BASIC_GROUP,
    HINT_CANNOT_POST,
    HINT_CHANNEL_NO_POST,
    HINT_FORUM_NOT_ADMIN,
    HINT_GONE,
    HINT_NO_TOPICS_RIGHT,
    HINT_NOT_FORUM,
    HINT_UNKNOWN,
    Chat,
    Topic,
    hints,
)
from wklabs.lib.delivery import (
    CATEGORY_ICON,
    ERR_FORBIDDEN,
    ERR_NO_RIGHTS,
    ERR_TOPIC_CLOSED,
    ERR_TOPIC_DELETED,
    PRESET_LABEL,
    Route,
)
from wklabs.lib.route_settings import help_line
from wklabs.lib.sync import SyncResult
from wklabs.lib.users import PENDING, TgUser

TOKEN_URL = "https://www.wanikani.com/settings/personal_access_tokens"


def _dt(dt: datetime | None, tz: ZoneInfo, fmt: str = "%d.%m %H:%M") -> str:
    return dt.astimezone(tz).strftime(fmt) if dt else "—"


def e(s: object) -> str:
    return escape(str(s))


# ------------------------------------------------------------------ start
def welcome_new(policy: str, tg_id: int) -> str:
    lines = [
        "👋 <b>wanikani-labs</b> — WaniKani progress tracker.",
        "I poll your account every 5 min and post digests: reviews, SRS moves, "
        "level-ups, content changes. A read-only token is enough.",
        "",
    ]
    if policy == "approve":
        lines.append("Access is by approval — request sent, I'll ping you when it's granted.")
    elif policy == "closed":
        lines.append("This bot is private. Ask the admin to let you in.")
    lines.append(f"your id: <code>{tg_id}</code>")
    return "\n".join(lines)


def welcome_no_accounts() -> str:
    return "👋 Hi! No WaniKani accounts yet."


def pending() -> str:
    return "⏳ Waiting for the admin to approve your access."


def access_granted() -> str:
    return "✅ Access granted — /accounts to add your WaniKani account."


def continue_private() -> str:
    return "Let's continue in private 👇"


def help_text() -> str:
    return (
        "<b>wanikani-labs bot</b>\n"
        "/accounts — your WaniKani accounts: add, rename, pause, delivery\n"
        "/chats — chats and forums I post to\n"
        "/status — levels, reviews due, last sync\n"
        "/help — this\n\n"
        f"<b>Token:</b> create one at {TOKEN_URL} — read-only is enough (leave all "
        "checkboxes off). Send it to me here in private; I delete your message at once "
        "and store the token encrypted.\n\n"
        "<b>Chats &amp; forums:</b> /chats — where I post. ➕ picks a chat from your list; "
        "Telegram adds me with the rights I need. In a forum choose a preset — one topic per "
        "category, per account, one for all, or General — then move any digest to any topic. "
        "I only know topics I created or saw messages in. Prefer commands? Add me to the chat "
        "and send /setup there.\n"
        "<b>Rights I need:</b> post messages; forums — admin + <i>Manage Topics</i>."
    )


# --------------------------------------------------------------- accounts
def accounts_list(accounts: list[Account]) -> str:
    if not accounts:
        return "👤 <b>Your accounts</b>\nnone yet — add one below"
    return "👤 <b>Your accounts</b>"


def account_card(
    acc: Account,
    routes: list[tuple[Route, Chat]],
    *,
    last_sync: datetime | None,
    tz: ZoneInfo,
    now: datetime,
) -> str:
    lines = [f"{acc.emoji} <b>{e(acc.label)}</b>   <code>{acc.key}</code>"]
    wk = f"WaniKani: {e(acc.username)} · level {acc.level or '?'}"
    lines.append(wk)
    if acc.status in (AUTH_ERROR, KEY_ERROR):
        lines.append(
            f"⚠️ token rejected ({e(acc.status_reason or acc.status)}) on "
            f"{_dt(acc.status_at, tz)} → 🔑 Replace token"
        )
    else:
        ago = f" ({int((now - last_sync).total_seconds() // 60)} min ago)" if last_sync else ""
        lines.append(
            f"token …{e(acc.token_hint)} · added {_dt(acc.created_at, tz, '%Y-%m-%d')} · "
            f"last sync {_dt(last_sync, tz)}{ago}"
        )
        if acc.status == "paused":
            lines.append("⏸ paused — not polling")
    if routes:
        for r, chat in routes:
            where = e(chat.name) + (f" › {e(r.thread_title)}" if r.thread_title else "")
            lines.append(f"{CATEGORY_ICON.get(r.category, '•')} {r.category} → {where}")
    else:
        lines.append("no delivery routes — 📬 Delivery")
    return "\n".join(lines)


def add_prompt(replace: Account | None = None) -> str:
    head = (
        f"🔑 Paste the new WaniKani API token for <b>{e(replace.label)}</b>."
        if replace
        else "🔑 Paste your WaniKani API token."
    )
    return (
        f"{head}\n"
        f"Create it at {TOKEN_URL} — read-only is enough (leave all checkboxes off).\n"
        "I delete your message with the token right away and store it encrypted."
    )


def not_a_token() -> str:
    return "That doesn't look like a WaniKani token (36 chars like 8f2c…-…). Try again or ✖️ Cancel."


def token_rejected() -> str:
    return "❌ WaniKani rejected this token. Check it's copied fully, or create a new one."


def token_error(exc: Exception) -> str:
    return f"❌ Could not check the token: {e(exc)}. Try again in a minute."


def token_other_user(ident: WkIdentity, expected: Account) -> str:
    return (
        f"That token belongs to <b>{e(ident.username)}</b>, not to {e(expected.label)}. "
        "To track it, add it as a separate account via /accounts → ➕."
    )


def token_foreign() -> str:
    return "This WaniKani account is already tracked by someone else. Ask the admin."


def admin_foreign_token(user: TgUser, acc: Account) -> str:
    return (
        f"⚠️ {e(user.display)} tried to add the WaniKani account {e(acc.label)} "
        f"(<code>{acc.key}</code>) owned by {acc.owner_tg_id}."
    )


def added_syncing(acc: Account, ident: WkIdentity) -> str:
    return (
        f"✅ <b>{e(ident.username)}</b> · level {ident.level} · "
        f"{e(ident.subscription_type or '?')}\n⏳ First sync running (≈20 s)…"
    )


def added_done(acc: Account, ident: WkIdentity, res: SyncResult, *, private: bool) -> str:
    per = res.stats.get(acc.key, {})
    got = " · ".join(
        f"{n} {name.replace('_', ' ')}"
        for name, st in per.items()
        if (n := st.fetched) and name in ("assignments", "review_statistics")
    )
    lines = [f"✅ <b>{e(ident.username)}</b> · level {ident.level} — synced: {got or 'ok'}"]
    if res.errors:
        lines.append("❌ " + e("; ".join(res.errors[:3])))
    if private:
        lines.append("Digests will arrive here, in this chat.")
        lines.append("Want a group or forum instead? /chats → ➕ Add a chat.")
    return "\n".join(lines)


def token_replaced(acc: Account, was: str) -> str:
    tail = " — account revived, digests resume." if was == "removed" else "."
    return f"🔑 Token replaced for <b>{e(acc.label)}</b>{tail}"


def rename_prompt(acc: Account) -> str:
    return f"✏️ New name for <b>{e(acc.label)}</b> (1–32 chars):"


def rename_bad() -> str:
    return "Name must be 1–32 characters. Try again or ✖️ Cancel."


def remove_confirm(acc: Account) -> str:
    return (
        f"Remove <b>{e(acc.label)}</b>? Digests stop; collected data stays "
        "(re-adding the same token restores everything). "
        "To delete data completely — ask the admin."
    )


def removed(acc: Account) -> str:
    return f"🗑 <b>{e(acc.label)}</b> removed. Data kept; add the token again to revive."


def _where(route: Route, chat: Chat) -> str:
    where = e(chat.name)
    if route.thread_id is not None and route.thread_title:
        where += f" › {e(route.thread_title)}"
    return where


def delivery(acc: Account, rows: list[tuple[Route, Chat]]) -> str:
    lines = [f"📬 <b>Delivery — {e(acc.label)}</b>"]
    if not rows:
        lines.append("no routes yet")
    for r, chat in rows:
        marks = " 🔕" if r.settings.get("silent") else ""
        marks += f" ⚠️ {e(r.error)}" if r.has_error else ""
        lines.append(f"{r.icon} {r.category} → {_where(r, chat)}{marks}")
    lines.append("")
    lines.append(
        "Tap a category to change where it goes or how. 📚 subjects = WaniKani content "
        "changes, shared per chat."
    )
    return "\n".join(lines)


def category_screen(acc: Account, category: str, rows: list[tuple[Route, Chat]]) -> str:
    icon = CATEGORY_ICON.get(category, "•")
    lines = [f"{icon} <b>{category} — {e(acc.label)}</b>"]
    if not rows:
        lines.append("goes nowhere yet — ➕ Also deliver to…")
    else:
        lines.append("Tap a target to switch it on/off, change the topic or settings.")
    return "\n".join(lines)


def route_card(
    route: Route, chat: Chat, label: str | None, *, note: str | None = None, view_only: bool = False
) -> str:
    lines = []
    if note:
        lines.append(note)
    head = f"{route.icon} <b>{route.category}</b>" + (f" — {e(label)}" if label else "")
    lines.append(head)
    where = f"→ {_where(route, chat)}" + ("" if route.enabled else " · off")
    if route.account is None:
        n = len(route.subscribers)
        where += f" · {n} subscriber{'s' if n != 1 else ''}"
    lines.append(where)
    if route.has_error:
        lines.append(f"⚠️ {ROUTE_ERRORS.get(route.error or '', e(route.error))}")
    if view_only:
        lines.append("view only — not your account")
    else:
        lines.append(help_line(route.category))
    return "\n".join(lines)


def pick_chat_target(label: str | None, category: str, *, mode: str) -> str:
    what = f"{CATEGORY_ICON.get(category, '•')} {category}" + (f" of {e(label)}" if label else "")
    if mode == "all":
        return f"Move all digests of <b>{e(label)}</b> to…"
    if mode == "add":
        return f"Also deliver {what} to…"
    return f"Where should {what} go?"


def pick_topic(chat: Chat, category: str) -> str:
    lines = [
        f"🗂 <b>{e(chat.name)}</b> — which topic for {CATEGORY_ICON.get(category, '•')} {category}?"
    ]
    if chat.topics_possible:
        lines.append("Auto topics follow the account name; picked ones I never rename or delete.")
    else:
        lines.append("I can't create topics here (see /chats) — pick a known one or General.")
    return "\n".join(lines)


def target_set(route: Route, chat: Chat) -> str:
    return f"✅ → {_where(route, chat)}"


def stale() -> str:
    return "This screen is stale — open 📬 Delivery again."


def not_allowed() -> str:
    return "not allowed for this route"


def routes_here(chat: Chat, n: int) -> str:
    return (
        f"🧭 <b>Routes into {e(chat.name)}</b> · {n}\n"
        "Tap one to change it (your own, or any if you admin this chat)."
    )


def topic_name_prompt(chat: Chat, rename: Topic | None) -> str:
    if rename:
        return f"✏️ New name for «{e(rename.name)}» in {e(chat.name)} (1–128 chars):"
    return f"➕ Name for the new topic in {e(chat.name)} (1–128 chars):"


def topic_name_bad() -> str:
    return "Topic name must be 1–128 characters. Try again or ✖️ Cancel."


def topic_created(name: str) -> str:
    return f"✅ Topic «{e(name)}» created."


def topic_renamed(old: str, new: str) -> str:
    return f"✅ «{e(old)}» → «{e(new)}»."


def topic_failed(exc: Exception) -> str:
    return f"❌ Telegram refused: {e(exc)}"


def rename_pick(chat: Chat) -> str:
    return f"✏️ Which topic in {e(chat.name)} to rename? (mine, or any if you admin the chat)"


# ------------------------------------------------------------------ chats
HINTS = {
    HINT_BASIC_GROUP: "💡 Topics need a supergroup: Group settings → Topics converts it "
    "(I follow the new id).",
    HINT_NOT_FORUM: "💡 Want one topic per account? Group settings → Topics, then 🔄 Refresh.",
    HINT_FORUM_NOT_ADMIN: "⚠️ Topics need me as admin with Manage Topics → then 🔄 Refresh.",
    HINT_NO_TOPICS_RIGHT: "⚠️ Missing right: Manage Topics → then 🔄 Refresh.",
    HINT_CANNOT_POST: "⚠️ I can't post here (restricted). Ask an admin to allow me.",
    HINT_CHANNEL_NO_POST: "⚠️ Need the Post Messages right.",
    HINT_GONE: "🚫 I'm no longer in this chat. Add me back or Forget it.",
    HINT_UNKNOWN: "ℹ️ Not checked yet → 🔄 Refresh.",
}
ROUTE_ERRORS = {
    ERR_TOPIC_CLOSED: "topic closed — reopen it or pick another target",
    ERR_TOPIC_DELETED: "topic deleted — delivering to General; ✨ Recreate or pick another",
    ERR_NO_RIGHTS: "can't post there — check my rights (🔄 Refresh in /chats)",
    ERR_FORBIDDEN: "I was removed from that chat",
}


def hint_lines(chat: Chat) -> list[str]:
    return [HINTS[h] for h in hints(chat) if h in HINTS]


def rights_line(chat: Chat) -> str:
    if chat.is_private:
        return ""
    if not chat.present:
        return f"me: {chat.status}"
    if not chat.inspected:
        return "me: not checked"
    who = "admin" if chat.is_admin else chat.status
    parts = [f"me: {who}", f"post {'✅' if chat.can_post else '✗'}"]
    if chat.is_forum:
        parts.append(f"topics {'✅' if chat.topics_possible else '✗'}")
    if chat.is_admin:
        parts.append(f"delete {'✅' if chat.rights.can_delete else '✗'}")
    return " · ".join(parts)


def chats_list(chats: list[Chat]) -> str:
    n = sum(1 for c in chats if not c.is_private)
    lines = ["💬 <b>Chats I can post to</b>" + (f" · {n}" if n else "")]
    lines.append("Don't see a chat? Add it with ➕, or send /setup there.")
    return "\n".join(lines)


def chat_card(
    chat: Chat,
    rows: list[tuple[Route, Account | None]],
    *,
    viewer: int,
    note: str | None = None,
) -> str:
    icon = (
        "🔒" if chat.is_private else ("📢" if chat.is_channel else ("🗂" if chat.is_forum else "👥"))
    )
    lines = []
    if note:
        lines.append(note)
    lines.append(f"{icon} <b>{e(chat.name)}</b> · {chat.kind}")
    rl = rights_line(chat)
    if rl:
        lines.append(rl)
    lines.extend(hint_lines(chat))
    live = [(r, a) for r, a in rows if r.enabled]
    if live:
        lines.append("Delivering here:")
        owners: set[int] = set()
        for r, acc in live:
            who = ""
            if acc is not None:
                owners.add(acc.owner_tg_id or 0)
                who = f" · {e(acc.label)}" + ("" if acc.owner_tg_id == viewer else " (theirs)")
            where = f" → {e(r.thread_title)}" if r.thread_id is not None and r.thread_title else ""
            err = f" ⚠️ {e(r.error)}" if r.has_error else ""
            if acc is None and r.subscribers:
                me = viewer in r.subscribers
                others = len(r.subscribers) - (1 if me else 0)
                who = " · you" if me else ""
                who += f" + {others}" if others else ""
            lines.append(f"{r.icon} {r.category}{who}{where}{err}")
        if len(owners) > 1:
            lines.append(f"{len(owners)} people deliver here")
    else:
        lines.append("Nothing delivered here yet.")
    if chat.is_forum and chat.present:
        extra = [f"topics known: {len(chat.topics)}"]
        if chat.preset:
            extra.append(f"last preset: {PRESET_LABEL.get(chat.preset, chat.preset)}")
        lines.append(" · ".join(extra))
    return "\n".join(lines)


def presets_screen(chat: Chat) -> str:
    lines = [f"📬 <b>Deliver to «{e(chat.name)}»</b> — all your accounts move here."]
    if chat.topics_possible:
        lines.append(
            "Pick a preset: topic per category (📝 Name · reviews, 🏆 Name · milestones), "
            "topic per account (Name), one topic for all (WaniKani), or General. "
            "You can move any digest to any topic afterwards."
        )
    elif chat.is_forum:
        lines.append("Topics need Manage Topics — for now digests go to General.")
    return "\n".join(lines)


def preset_done(labels: list[str], created: list[str], reused: int, general: bool) -> str:
    who = ", ".join(e(x) for x in labels) or "nothing"
    parts = [f"✅ {who} → here"]
    if created:
        parts.append(f"{len(created)} topic(s) created: " + ", ".join(e(x) for x in created))
    if reused:
        parts.append(f"{reused} existing topic(s) reused")
    if general and not created and not reused:
        parts.append("as one stream")
    return " · ".join(parts)


def setup_light(chat: Chat, *, accounts: int) -> str:
    lines = [f"🛠 <b>{e(chat.name)}</b> · {chat.kind} · {rights_line(chat)}"]
    lines.extend(hint_lines(chat))
    if accounts == 0:
        lines.append("You have no WaniKani accounts yet — add one in private: /accounts.")
    elif chat.can_post:
        lines.append("Deliver your digests here with one tap, or configure in detail.")
    return "\n".join(lines)


def pick_chat() -> str:
    return (
        "Pick where I should post 👇\n"
        "If I'm not there yet, Telegram adds me with the rights I need "
        "(admin + Manage Topics for forums).\n"
        "Prefer commands? Add me to the chat and send /setup there."
    )


def picked(title: str | None) -> str:
    return f"✅ «{e(title)}»" if title else "✅ picked"


def pick_absent() -> str:
    return "I'm not in that chat. If you're its admin, add me there; otherwise ask an admin."


def pick_cancelled() -> str:
    return "Cancelled."


def stop_confirm(chat: Chat, labels: list[str]) -> str:
    who = ", ".join(e(x) for x in labels)
    return (
        f"Stop delivering {who} to «{e(chat.name)}»? Digests go back to your private chat "
        "if nowhere else. I stay in the chat."
    )


def stopped(chat: Chat, n: int) -> str:
    return f"🚫 {n} route(s) to «{e(chat.name)}» switched off."


def forgotten(chat: Chat) -> str:
    return f"🗑 «{e(chat.name)}» forgotten. If I'm added there again, it comes back."


def topics_list(chat: Chat) -> str:
    lines = [f"🧵 <b>Topics — {e(chat.name)}</b> · {len(chat.topics)} known"]
    for t in sorted(chat.topics.values(), key=lambda x: x.thread_id):
        tags = " · by me" if t.by_bot else ""
        tags += " · closed" if t.closed else ""
        lines.append(f"• {e(t.name)}{tags}")
    lines.append("")
    lines.append(
        "I only see topics I created or saw messages in — post anything in a topic and it "
        "appears here."
    )
    if not chat.topics_possible:
        lines.extend(hint_lines(chat))
    return "\n".join(lines)


def test_message() -> str:
    return "✅ test · wanikani-labs"


def test_result(error: str | None) -> str:
    return "✅ sent" if error is None else f"❌ {error}"


def greet_dm(chat: Chat) -> str:
    return f"👋 I'm in «{e(chat.name)}» now · {chat.kind} · {rights_line(chat)}\n" + "\n".join(
        hint_lines(chat)
    )


def greet_chat() -> str:
    return "Hi! WaniKani digests here → /setup, or open me in private → /chats."


def removed_from_chat(chat_name: str, labels: list[str]) -> str:
    who = ", ".join(e(x) for x in labels)
    return f"🚫 Removed from «{e(chat_name)}» — {who} paused there. /chats to pick another."


def route_error(route: Route, chat_name: str, label: str | None) -> str:
    what = f"{route.icon} {route.category}" + (f" · {e(label)}" if label else "")
    return f"⚠️ {what} → «{e(chat_name)}»: {ROUTE_ERRORS.get(route.error or '', e(route.error))}"


def recreated(name: str) -> str:
    return f"✨ Topic «{e(name)}» recreated — digests go there again."


# ------------------------------------------------------------------ admin
def admin_home() -> str:
    return "🛠 <b>Admin</b>"


def admin_users(users: list[TgUser]) -> str:
    return f"👥 <b>Users</b> · {len(users)}"


def admin_user(u: TgUser, accounts: list[Account]) -> str:
    lines = [f"👤 <b>{e(u.display)}</b> · {u.status}" + (" · admin" if u.is_admin else "")]
    if accounts:
        lines.append("accounts: " + ", ".join(f"{a.emoji} {e(a.label)}" for a in accounts))
    else:
        lines.append("no accounts")
    return "\n".join(lines)


def admin_accounts(accounts: list[Account]) -> str:
    return f"🗂 <b>Accounts</b> · {len(accounts)}"


def new_user(u: TgUser) -> str:
    what = "Access request" if u.status == PENDING else "joined"
    return f"🆕 {what}: {e(u.display)}"


def sync_result(res: SyncResult) -> str:
    took = (res.finished_at - res.started_at).total_seconds() if res.finished_at else 0
    text = (
        f"{'✅' if res.ok else '❌'} {res.kind} in {took:.1f}s · fetched {res.total('fetched')}"
        f" · new {res.total('new')} · changed {res.total('changed')} · "
        f"events {len(res.events)} · requests {res.requests}"
    )
    if not res.stats:
        text += " · no active accounts"
    if res.errors:
        text += "\n" + "\n".join(f"• {e(x)}" for x in res.errors[:5])
    return text
