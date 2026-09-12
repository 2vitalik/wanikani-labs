"""Bot texts (Telegram HTML, EN). Pure functions — no I/O."""

from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from wklabs.lib.accounts import AUTH_ERROR, KEY_ERROR, Account, WkIdentity
from wklabs.lib.delivery import CATEGORY_ICON, LAYOUT_TOPICS, Chat, Route
from wklabs.lib.sync import SyncResult
from wklabs.lib.users import PENDING, TgUser

from .keyboards import SetupState

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
        "/status — levels, reviews due, last sync\n"
        "/help — this\n\n"
        f"<b>Token:</b> create one at {TOKEN_URL} — read-only is enough (leave all "
        "checkboxes off). Send it to me here in private; I delete your message at once "
        "and store the token encrypted.\n\n"
        "<b>Forum with topics:</b> add me to a forum as admin with <i>Manage Topics</i> "
        "and send /setup there — each account gets its own topics.\n"
        "<b>Group:</b> same, /setup — digests go to the group as one stream."
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
        lines.append(
            "Want topics in a forum instead? Add me there as admin (Manage Topics) and send /setup."
        )
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


def delivery(acc: Account, rows: list[tuple[Route, Chat]]) -> str:
    lines = [f"📬 <b>Delivery — {e(acc.label)}</b>"]
    if not rows:
        lines.append("no routes yet")
    for r, chat in rows:
        where = e(chat.name) + (f" › {e(r.thread_title)}" if r.thread_title else "")
        icon = CATEGORY_ICON.get(r.category, "•")
        lines.append(f"{'✅' if r.enabled else '🚫'} {icon} {r.category} → {where}")
    lines.append("")
    lines.append("📚 subjects = WaniKani content changes (per chat).")
    lines.append("+ another chat: add me there and send /setup.")
    return "\n".join(lines)


# ------------------------------------------------------------------ setup
def setup_screen(chat: Chat, st: SetupState, *, mine: int) -> str:
    kind = "forum" if chat.is_forum else chat.type
    rights = (
        "I can manage topics ✅"
        if chat.topics_possible
        else (
            "forum, but I need admin with Manage Topics for per-account topics"
            if chat.is_forum
            else ""
        )
    )
    lines = [f"🛠 <b>Setup — «{e(chat.name)}»</b> · {kind}" + (f" · {rights}" if rights else "")]
    if mine == 0:
        lines.append("You have no accounts yet — add one in private (/accounts).")
    else:
        lines.append(
            "Tick the accounts to deliver here; their digests move from wherever they go now."
        )
    if st.layout == LAYOUT_TOPICS:
        lines.append("Layout: one topic per account and category.")
    else:
        lines.append("Layout: everything as one stream in this chat.")
    return "\n".join(lines)


def setup_done(chat: Chat, st: SetupState, created: list[str], labels: list[str]) -> str:
    lines = ["✅ Setup applied."]
    if labels:
        lines.append("Delivering here: " + ", ".join(e(x) for x in labels) + ".")
    else:
        lines.append("No accounts delivered here.")
    if created:
        lines.append(f"{len(created)} topic(s) created: " + ", ".join(e(x) for x in created))
    return "\n".join(lines)


def setup_cancelled() -> str:
    return "Setup cancelled — nothing changed."


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
