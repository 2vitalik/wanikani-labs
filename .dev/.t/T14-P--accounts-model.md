# T14 · Акаунти в Mongo: модель, схема, міграція, безпека токенів, код

`2026-09-11` · 💡 proposal

Контекст:
- запит у чаті 2026-09-11: акаунти зараз прошиті в `.env` (`WK_TOKEN__MAIN/LIGHT`); треба, щоб акаунтів спочатку не було, їх додавали через бота, можна кілька, ними керували; будь-який майбутній користувач має отримати те, що зараз маю я, а я — легко цим керувати;
- фон — [T07](T07-P--bot-vision.md) §0 і §4 (multi-user, модель «користувач → акаунти → призначення», токени в Mongo з шифруванням); архітектура v1 — [T01](T01-P--architecture-v1.md);
- стан коду (перевірено): `Settings.wk_token` → `SyncEngine(db, tokens)`; `TopicManager(accounts)` створює топіки `<acc>.reviews/milestones` у `TG_FORUM_CHAT_ID`; `Notifier` групує події за ключем топіка; `IsAdmin` — `TG_ADMIN_IDS`; бот без акаунтів падає (`SystemExit`);
- локальна Mongo: `users._id ∈ {main, light}`, `history.account ∈ {null, main, light}` (218 704 версії), `sync_state._id = "<acc>:<resource>"`, `tg_topics` порожня (реального Telegram ще не було); `main` = Vitalik L39 (`wk_id 07fff792-…`), `light` = 2vitalik L7 (`27f9b9f5-…`);
- UX — [T15](T15-P--bot-ux-accounts.md); альтернативи з аргументами — [T16](T16-B--accounts-alternatives.md); питання — [T17](T17-Q--accounts-questions.md); план реалізації — [T18](T18--accounts-v1/plan.md).

## 1. Сутності

Чотири: **TG-користувач** (хто говорить з ботом) → володіє **акаунтами** WK (токен) → отримує повідомлення в **чатах** (приват / група / форум) за **маршрутами** (акаунт × категорія → чат + топік).

- `tg_users` — люди: роль (`admin` / `user`), статус доступу (`pending` / `active` / `blocked`).
- `accounts` — акаунти WaniKani: ключ, ідентичність WK (`wk_id`), зашифрований токен, власник, статус, кеш `username`/`level`.
- `chats` — чати, де бот доставляє: тип, чи форум, чи є права на топіки, розкладка (`topics` / `single`), хто налаштував.
- `routes` — куди йде категорія повідомлень: `(account | null, category) → (chat_id, thread_id)`, вмикається/вимикається. Узагальнення нинішніх `routing.py` + `tg_topics`.
- `tg_topics` — реєстр створених ботом топіків (`chat_id, thread_id, title, purpose`), щоб не створювати двічі й перейменовувати.

Категорії — це «канали» доставки, не види подій; `routing.py` мапить `kind → category`:

| категорія | scope | що | зараз |
|---|---|---|---|
| `reviews` | акаунт | reviewed · srs_up · srs_down · unlocked · started | топік `<acc>.reviews` |
| `milestones` | акаунт | passed · burned · resurrected · level_* · user_level · reset | топік `<acc>.milestones` |
| `subjects` | глобальна, opt-in на чат | subject_new · subject_updated · subject_hidden | топік `subjects` |
| `system` | глобальна, лише адміни | помилки sync, heartbeat, запити доступу | топік `system` |
| `daily` · `sessions` · `reminders` | акаунт | резерв під крок 2 [T07](T07-P--bot-vision.md) | — |

## 2. Схема Mongo

```
accounts
  _id          "main" | "light" | "07fff792"   # ключ; незмінний; = поле `account` у history/events/assignments/…
  wk_id        "07fff792-eea6-…"               # UUID з /user; unique
  username     "Vitalik"      level 39         # кеш з /user (оновлює sync)
  label        "Vitalik"                       # імʼя для людини; редагується; дефолт = username
  token        {enc: "<fernet>", hint: "ab12", added_at, key_id: 1}
  owner_tg_id  123456789                       # хто додав; null для env-імпорту без адмінів
  status       "active" | "paused" | "auth_error" | "removed"
  status_reason, status_at
  source       "env" | "bot" | "cli"
  created_at, updated_at
  settings     {}                              # шар «акаунт» з T07 §4 — поки порожній

tg_users
  _id          tg user id
  username, first_name, lang
  role         "admin" | "user"                # admin — дзеркало TG_ADMIN_IDS + грант через бота
  status       "pending" | "active" | "blocked"
  created_at, last_seen_at, approved_by, approved_at

chats
  _id          chat id (приват = tg user id; група/форум = -100…)
  type         "private" | "group" | "supergroup"
  title, is_forum, bot_is_admin, can_manage_topics   # оновлюється при /setup і на помилках надсилання
  layout       "topics" | "single"             # topics — лише форум із правами
  set_up_by    tg user id
  created_at, checked_at

routes
  _id          ObjectId
  account      "main" | null                   # null = глобальна категорія
  category     "reviews" | "milestones" | "subjects" | "system" | …
  chat_id, thread_id (null = без топіка)
  enabled      true
  created_by, created_at
  settings     {}                              # шар «призначення» з T07 §4
  unique (account, category, chat_id)

tg_topics
  _id          "<chat_id>:<thread_id>"
  chat_id, thread_id, title
  purpose      {account, category}             # щоб перейменувати при зміні label
  created_at
```

Індекси: `accounts.wk_id` unique · `accounts (owner_tg_id, status)` · `routes (account, category, enabled)` · `routes (chat_id, thread_id)` · `tg_users.status`.

Що **не** міняється: `assignments` / `review_statistics` / … / `history` / `events` — поле `account` як було; `sync_state._id = "<acc>:<resource>"`; `users._id` / `summaries._id` = ключ. Це головний аргумент лишити ключі `main`/`light`: жодної міграції 218 704 версій.

### Ключ акаунта

- Для нових — детермінований з ідентичності WK: `key = wk_id[:8]` (`07fff792`). Наслідок: повторне додавання того самого акаунта після видалення дає той самий ключ → історія зшивається сама. Колізія 8 hex практично неможлива, при додаванні перевіряється.
- Для двох наявних — `main` і `light` (мапа `wk_id → key` лежить у документі `accounts`; ці документи ніколи не видаляти фізично — лише `status: removed`, інакше re-add створить `07fff792` і осиротить історію `main`).
- Ключ — для машини (логи, `sync_state`, `history`); людині показується `label`. Ключ ніколи не вводить користувач.

### Статуси акаунта й sync

- `active` — поллиться. `paused` — користувач зупинив (не поллиться, дані лишаються). `auth_error` — WK відповів 401/403: пол зупиняється, власнику одне повідомлення «token rejected → /accounts → 🔑 Replace token», бот не стукає в WK щопʼять хвилин. `removed` — знято з UI, дані лишаються (purge — §5).
- Baseline-логіка `sync_state` уже правильна для додавання: перший sync нового акаунта записує версії **без подій** (немає потопу з 9 000 «unlocked»). Повернення `paused → active` продовжує інкремент з `updated_after` → події за пропущений період виводяться (це фіча: нічого не губиться).

## 3. Токени: безпека

- **Шифрування at rest:** Fernet (`cryptography`), ключ — `WKLABS_SECRET_KEY` в env (`wklabs gen-key` друкує новий). Без ключа бот не стартує зі зрозумілою помилкою; CLI-команди без токенів (`import-files`, `rebuild-events`, `status`) ключа не потребують (cipher ліниво). Навіщо: `mongodump` бази регулярно їздить між машинами (runbook §8, Dropbox) — дамп із відкритими токенами = ключі від акаунтів у кожній копії. `key_id` у документі — задел під ротацію.
- **Ввід токена — лише в приваті з ботом.** Бот одразу видаляє повідомлення з токеном (у приваті це дозволено до 48 год). У групі/форумі токен не приймається: «write me in private»; якщо бот має право — видаляє повідомлення; завжди радить відкликати такий токен на WK.
- Формат перевіряється до звернення в API (UUID, 36 символів); далі `GET /user` → 401 = невалідний. Успіх дає `wk_id`, `username`, `level`, `subscription`.
- Дублікат `wk_id`: той самий власник → пропозиція замінити токен (ротація; ключ і дані ті самі); інший власник → відмова + повідомлення адмінам у `system` (шеринг акаунта між людьми — пізніше, T07 §4).
- Ніколи не логувати й не показувати токен; лише `hint` (останні 4 символи) — як зараз у `wklabs accounts`.
- Права токена WK через API не видно (T07 §4); write-можливості перевіряються спробою — поза цим тікетом.
- Callback data кнопок підробляється тривіально → кожен хендлер перевіряє, що акаунт належить тому, хто натиснув (або адмін).
- Користувач заблокував бота (`TelegramForbiddenError`) → маршрути в цей чат вимикаються; акаунт → `paused` після N поспіль (не гріти WK даремно).

## 4. Доступ і ролі

- `TG_ADMIN_IDS` лишається в env як bootstrap-адміни (себе не залочиш); на старті дзеркалиться в `tg_users.role = admin`.
- Політика доступу для нових людей — `ACCESS_POLICY` (env, дефолт `approve`): `approve` — `/start` створює `pending`, адміни отримують картку з ✅/🚫; `open` — одразу `active`; `closed` — лише адмін додає id. Рекомендація — `approve` ([T17](T17-Q--accounts-questions.md) Q1). Перемикач у `/admin` — пізніше.
- Права: `user` бачить і керує лише своїми акаунтами й чатами, які сам налаштував; `admin` — усе (`/admin`: користувачі, всі акаунти, sync, статус) плюс `system`-маршрут.

## 5. Видалення й дані

- `🗑 Remove` у боті = `status: removed` + видалення маршрутів; дані (assignments, history, events) лишаються; топіки форуму не чіпаємо. Повернути — додати той самий токен (revive за `wk_id`).
- **Purge** (фізичне видалення per-account даних: `assignments · review_statistics · level_progressions · study_materials · resets · history · events · sync_state · users · summaries · routes`) — лише CLI `wklabs accounts purge <key> --yes` і лише для `status: removed`. Глобальне (`subjects`, `history` з `account = null`) не чіпається. У боті кнопки purge немає ([T17](T17-Q--accounts-questions.md) Q4) — від випадкового знищення 218 704 версій це страхує краще за будь-який confirm.

## 6. Bootstrap і міграція з env

На старті бота (і в `wklabs accounts import-env`) — ідемпотентно:

1. Для кожного `WK_TOKEN__<KEY>`: якщо `accounts._id = key` нема → `GET /user` → створити (`source: env`, `owner_tg_id = TG_ADMIN_IDS[0]` або null, `label` = username WK). Є → нічого: Mongo — джерело істини, env більше не перебиває. У лог: `imported main from env — WK_TOKEN__MAIN can be dropped`.
2. Якщо `TG_FORUM_CHAT_ID` є і в `chats` його нема → створити чат (`layout: topics`, `set_up_by` = перший адмін), маршрути `reviews`/`milestones` для env-акаунтів + `subjects` + `system` у цей чат; `thread_id` беруться зі старих `tg_topics._id = "<acc>.<cat>"`, якщо є (на vv3, схоже, ще нема), інакше топік створюється при першому надсиланні.
3. Далі `TG_FORUM_CHAT_ID` і `WK_TOKEN__*` в env — необовʼязкові (лишаються для повторного bootstrap на чистій базі, напр. локально).

Бот стартує і з нулем акаунтів: планувальник працює, sync — no-op з логом `no active accounts`.

## 7. Код

`lib` (чисте, без Telegram):
- `crypto.py` — `TokenCipher(key).encrypt / decrypt`, `generate_key()`.
- `accounts.py` — `Account` (dataclass) + `AccountRepo(db, cipher)`: `get · by_wk_id · for_owner · list(status) · create · set_token · set_status · set_label · remove · purge`; `key_for(wk_id)`; `validate_token(token) -> WkIdentity` (один `GET /user`).
- `users.py` — `TgUserRepo`: `ensure(from_user)` (upsert + `last_seen_at`), `set_status`, `admins()`.
- `delivery.py` — `ChatRepo`, `RouteRepo`: `routes_for(account, category)`, `default_routes(account, chat)`, `toggle`, `move(account, chat)`.
- `sync.py` — `SyncEngine(db, accounts: AccountRepo)`: клієнти будуються з активних акаунтів на кожен `run` (кеш за хешем токена); глобальні ресурси — токеном першого активного; 401/403 → `accounts.set_status(auth_error)`. Для тестів — `SyncEngine.from_tokens(db, {...})` (статичний репо), щоб `test_sync.py` не переписувати.
- `status.py` — приймає список акаунтів, не `settings`.
- `settings.py` — `+ secret_key`, `+ access_policy`; `wk_token`, `tg_forum_chat_id` лишаються як bootstrap.
- `db.py` — колекції/індекси з §2. `bootstrap.py` — §6.

`bot`:
- `handlers/` → `start.py` (public: /start, /ping, deep-link), `accounts.py` (/accounts, картка, add/rename/replace/pause/remove), `setup.py` (/setup у чаті), `admin.py` (/admin, approve/block, /sync), `status.py`. Спільне — `filters.py` (`IsActive`, `IsAdmin`, `PrivateChat`), `callbacks.py` (`CallbackData` з префіксами `acc`, `rt`, `adm`, `setup`, `nav`), `keyboards.py`, `texts.py`.
- `middleware.py` — `UserMiddleware`: upsert `tg_users`, кладе `user` у data; `pending` / `blocked` отримують одну відповідь і далі ігноруються.
- `routing.py` — `category_for(kind)`; `notifier.py` — групує події за `(account, category)` → `routes_for` → рендер (з `label`) → надсилання в кожен маршрут; `events.delivered: [route_id]` для ідемпотентності при падінні посередині; без маршрутів → `skipped`.
- `topics.py` → `TopicManager.ensure_topic(chat_id, account, category) -> thread_id` (створює, пише `tg_topics`), `rename(account, label)`.
- `context.py` — `+ accounts, users, chats, routes, cipher`; `run_sync(accounts=[key])` для першого sync щойно доданого.
- `__main__.py` — bootstrap → без `SystemExit` при нулі акаунтів → команди меню за scope (приват / групи / адміни).
- FSM — `MemoryStorage` (діалоги на один крок: токен, назва; рестарт посеред = «спробуй ще»; те, що має жити, — уже в Mongo).

`cli`: `wklabs accounts list | add --owner <tg_id> (токен зі stdin) | import-env | pause | resume | remove | purge --yes`, `wklabs gen-key`.

Тести: cipher roundtrip · `AccountRepo` (create / dup / revive / purge не чіпає глобальне) · bootstrap ідемпотентний · `SyncEngine` з репо + 401 → `auth_error` · `Notifier` за маршрутами (приват + форум + вимкнений) · клавіатури/тексти чисті.

## 8. Масштаб і межі

- Sync — послідовний по акаунтах; ~7 запитів × ~0.3 с на акаунт за пол → до ~50 акаунтів у 5-хвилинне вікно без змін; далі — `gather` із семафором по акаунтах (ліміт WK — на токен, тож паралель безпечна).
- Перший sync акаунта ≈ 25 запитів / ~10 с — запускається одразу після додавання під `sync_lock` (чекає планового, якщо той іде).
- Локальний бот і vv3 з тими самими WK-токенами — ок (ліміт на токен); з тим самим `BOT_TOKEN` — `TelegramConflictError` (runbook §6).
- Restore дампу на іншій машині потребує того ж `WKLABS_SECRET_KEY` — інакше акаунти переходять в `auth_error` і токени перевводяться (їх одиниці).

## Твої думки та питання

> 
