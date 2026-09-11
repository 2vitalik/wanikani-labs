# T15 · UX бота для акаунтів: команди, меню, діалоги, екрани

`2026-09-11` · 💡 proposal

Контекст:
- модель і схема — [T14](T14-P--accounts-model.md); бачення — [T07](T07-P--bot-vision.md) §0 («усе налаштовується через бота; дефолти розумні»), §4, §7 (інлайн-клавіатури);
- нинішні команди: `/start` `/ping` (публічні), `/status` `/sync` `/sync_full` `/topics` `/help` (адмін); тексти бота — EN (публічний реліз — EN дефолт, T07 §8);
- принципи: мало команд + один хаб із кнопками; діалоги (FSM) лише там, де потрібен ввід тексту (токен, назва); меню — лише в приваті; у групі/форумі — тільки `/setup`, `/status`, `/ping`.

## 1. Команди (меню BotFather — за scope)

Приват, усі активні:
- `/start` — онбординг або головне меню (deep-link `/start setup_<chat_id>` — продовження `/setup` з групи).
- `/accounts` — список акаунтів → картка → дії. Головний екран.
- `/status` — мої акаунти: рівень, due, останній sync (адмін — ще й лічильники бази).
- `/help` — що вміє, як створити токен, як підключити форум.

Приват, адміни: `/admin` — користувачі (pending), усі акаунти, sync, статус; `/sync`, `/sync_full` лишаються.

Групи/форуми: `/setup` — доставляти сюди; `/status`; `/ping`. Решта команд у групі → «continue in private» + кнопка з deep-link.

`/topics` зникає (топіки створюються через `/setup` і маршрути).

## 2. Екрани

Кнопки — inline; `«` завжди повертає на попередній екран редагуванням того самого повідомлення (один «живий» екран меню на чат, без стосу повідомлень).

**`/start` — новий користувач, `ACCESS_POLICY=approve`**
```
👋 wanikani-labs — WaniKani progress tracker.
I poll your account every 5 min and post digests: reviews, SRS moves,
level-ups, content changes. A read-only token is enough.

Access is by approval — request sent, I'll ping you when it's granted.
your id: 123456789
```
Адмінам у `system` (або в приват, якщо `system`-маршруту нема):
```
🆕 Access request: Vitalik (@name · 123456789)
[✅ Approve]  [🚫 Block]
```
Після approve — користувачу: `✅ Access granted — /accounts to add your WaniKani account.`

**`/start` — активний, акаунтів нема**
```
👋 Hi! No WaniKani accounts yet.
[➕ Add account]   [ℹ️ How it works]
```

**`/accounts`**
```
👤 Your accounts
[🟢 Vitalik · L39 · 12 due]
[🟢 2vitalik · L7 · 0 due]
[⏸ old · L3]
[➕ Add account]
```
Статус: 🟢 active · ⏸ paused · ⚠️ auth_error (токен відкликано).

**Картка акаунта**
```
🟢 Vitalik   (main)
WaniKani: Vitalik · level 39 · lifetime
token …ab12 · added 2026-09-12 · last sync 14:05 ✅ (3 min ago)
📝 reviews     → WK forum › 📝 Vitalik · reviews
🏆 milestones  → WK forum › 🏆 Vitalik · milestones

[📬 Delivery]  [✏️ Rename]  [🔑 Replace token]
[⏸ Pause]      [🗑 Remove]
[« Accounts]
```
У стані `auth_error` замість рядка токена: `⚠️ token rejected by WaniKani (401) on 09-12 14:05 → 🔑 Replace token`.

**➕ Add account** (FSM `AddAccount.token`; лише приват)
```
🔑 Paste your WaniKani API token.
Create it at wanikani.com/settings/personal_access_tokens —
read-only is enough (leave all checkboxes off).
I delete your message with the token right away and store it encrypted.
[✖️ Cancel]
```
Користувач надсилає токен → бот видаляє повідомлення → перевірка:
- не схоже на токен → `That doesn't look like a WaniKani token (36 chars like 8f2c…-…). Try again or ✖️ Cancel.`
- 401 → `❌ WaniKani rejected this token. Check it's copied fully, or create a new one.`
- уже є в тебе → `This is Vitalik (already added). Replace its token? [🔑 Replace] [✖️ Cancel]`
- є в іншого → `This WaniKani account is already tracked by someone else. Ask the admin.` (+ картка адмінам у `system`).
- ок:
```
✅ Vitalik · level 39 · lifetime
⏳ First sync running (≈20 s)…
```
→ те саме повідомлення редагується:
```
✅ Vitalik · level 39 — synced: 9 305 assignments, 8 973 review stats.
Digests will arrive here, in this chat.
Want topics in a forum instead? Add me there as admin (Manage Topics)
and send /setup.
[👤 Accounts]
```

**✏️ Rename** (FSM `Rename.label`) — `New name for Vitalik:` → 1–32 символи → перейменовує акаунт і його топіки (`edit_forum_topic`).

**🔑 Replace token** — той самий діалог, що Add; `wk_id` має збігтися, інакше `That token belongs to another WaniKani user (2vitalik). Add it as a separate account? [➕ Add] [✖️ Cancel]`.

**⏸ Pause / ▶️ Resume** — одна кнопка-перемикач; негайно, без підтвердження (оборотно).

**🗑 Remove** — двокроково:
```
Remove Vitalik? Digests stop; collected data stays (re-adding the same
token restores everything). To delete data completely — ask the admin.
[🗑 Yes, remove]  [« Back]
```

**📬 Delivery** (з картки акаунта)
```
📬 Delivery — Vitalik
📝 reviews      → here (private)     [✅ on]
🏆 milestones   → here (private)     [✅ on]
📚 subjects     → here (private)     [🚫 off]   WK content changes · per chat
Move all to:  [WK forum]  [private]
+ another chat: add me there and send /setup
[« Back]
```
`[✅ on]` / `[🚫 off]` — перемикач `routes.enabled`. «Move all» — переносить маршрути акаунта в інший чат цього користувача (`chats.set_up_by`).

**`/setup` — у групі/форумі** (від активного користувача; бот перевіряє `get_chat_member(me)`)
```
🛠 Setup — «WK forum» · forum · I can manage topics ✅
Deliver here:
[☑ Vitalik]  [☐ 2vitalik]
Layout:  [● topics per account]  [○ single stream]
[☑ 📚 subjects]   [☑ 🛠 system]
[✅ Apply]  [✖️ Cancel]
```
`🛠 system` — лише адмінам. Apply → створюються топіки (`📝 Vitalik · reviews`, `🏆 Vitalik · milestones`, `📚 subjects`, `🛠 system`), маршрути переїжджають → `✅ 4 topics created. Digests for Vitalik go here now.` Звичайна група → лише `single stream`; форум без прав → `single stream` + підказка дати право Manage Topics. Повторний `/setup` — редагування (галочки з поточних маршрутів).

**`/status`** — як зараз, але блоки — лише акаунти того, хто питає (адмін: усі + рядок `db:` + pending events).

**`/admin`**
```
🛠 Admin
[👥 Users 3 · pending 1]  [🗂 Accounts 4]
[🔄 Sync now]  [🔄 Full sync]  [📈 Status]
```
Users → список `✅ Vitalik (admin) · ⏳ someone · 🚫 spam` → картка: `[✅ Approve] [🚫 Block] [👑 Make admin]`. Accounts → усі акаунти з власником і статусом → та сама картка акаунта (адмін має всі кнопки).

## 3. Правила поведінки

- Меню — лише в приваті. Команда меню в групі → `Let's continue in private → [Open chat]` (deep-link).
- Токен у групі → не приймається; якщо бот може — видаляє повідомлення; завжди: `Please revoke this token on WaniKani and send a new one to me in private.`
- Кожна кнопка перевіряє власника акаунта / роль (callback data — не довіряти).
- `pending` — одна відповідь `waiting for approval` на будь-що; `blocked` — тиша (лог).
- Один «екран» на чат: відповіді на кнопки — `edit_text` того самого повідомлення; нові повідомлення — лише для дайджестів і результатів довгих операцій (перший sync).
- Мова — EN (як зараз); i18n — T07 §8, не зараз.

## 4. Callback data (aiogram `CallbackData`)

`acc:<key>:<action>` (`card · delivery · rename · token · pause · remove · remove_yes · move:<chat_id>`) · `rt:<route_id>:toggle` · `setup:<chat_id>:<field>:<value>` · `adm:user:<id>:<approve | block | admin>` · `nav:<screen>`. Усе ≤ 64 байт.

## Твої думки та питання

> 
