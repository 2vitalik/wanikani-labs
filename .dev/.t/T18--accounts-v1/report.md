# T18 · Акаунти v1: users/accounts/chats/routes + UI бота — звіт

`2026-09-12` · ⚙️ задача · готово (код), деплой на vv3 — твій крок

Рішення, за якими робилось, — [T21](../T21-R--accounts-decisions.md); дизайн — [T14](../T14-P--accounts-model.md) з правками [T19](../T19-C--accounts-answers.md), UX — [T15](../T15-P--bot-ux-accounts.md).

## Зроблено

**lib**
- `settings.py`: без `wk_token`/`tg_forum_chat_id`; `+ wklabs_secret_key` (env `WKLABS_SECRET_KEY`), `+ access_policy` (`open` дефолт).
- `crypto.py` — `TokenCipher` (Fernet), `generate_key`; залежність `cryptography` у `wklabs-lib`.
- `db.py` — колекції `accounts · tg_users · tg_chats · tg_routes · tg_fsm`, індекси (`accounts.wk_id` unique, `tg_routes (account, category, chat_id)` unique); `tg_topics` прибрано.
- `accounts.py` — `WkIdentity`, `validate_token` (один `GET /user`; 401/403 → `InvalidTokenError`), `key_for` (`wk_id[:8]`, колізія → 12), `AccountRepo` (create / set_token / set_status / set_label / set_owner / remove / purge + `TokenSource`: `active_tokens` з `key_error` при чужому ключі, `on_auth_error`, `on_user_seen`), `delete_account_data`, `rename_key`, `migrate_keys`.
- `users.py` — `TgUserRepo` (upsert на кожен апдейт, роль з `TG_ADMIN_IDS`, початковий статус за політикою, `counts`, `admin_ids_all`).
- `delivery.py` — категорії, `Chat`/`ChatRepo` (`ensure_private`, `for_user`), `Route`/`RouteRepo` (`for_target`, `upsert`, `move_account`, `suspend_account`/`resume_account` — вимикання з памʼяттю, `disable_chat`), `topic_title`.
- `sync.py` — `SyncEngine(db, source | dict)`: клієнти з `TokenSource` на кожен run (кеш за токеном), без акаунтів — тихий no-op, 401/403 → `on_auth_error` і стоп по акаунту, `user` → `on_user_seen`.
- CLI: `wklabs accounts list | add [--owner] | pause | resume | remove | purge --yes | migrate-keys [--dry-run]`, `wklabs gen-key`; `sync`/`status` через репо; `import-files`/`import-raw` без дефолтів `main`/`light`.

**bot**
- `routing.py` → `category_for`/`target_for`; `topics.py` → `TopicManager` (`ensure_thread` при першій доставці, `ensure_chat_topics` після `/setup`, `rename_account`); `notifier.py` → доставка за маршрутами, `events.delivered` per route, `skipped`/`no_route`, `TelegramForbiddenError` → маршрути чату off, зниклий топік → `thread_id` скидається; `system` → маршрути `system` або приват адмінів.
- `middleware.py` — `UserMiddleware`: upsert користувача, `blocked` → тиша, `pending` → одна відповідь, новий → адмінам `🆕 joined`/`Access request` з кнопками.
- `handlers/`: `start` (`/start`, `/ping`, `/help`, `/status`, «continue in private» у групах), `accounts` (список, картка, add з видаленням повідомлення й першим sync у тому ж повідомленні, детектор UUID-токена поза станом, rename з перейменуванням топіків, replace token, pause/resume, remove у два кроки, delivery: on/off per маршрут, `📚 subjects` per чат, move all), `setup` (`/setup` у групі/форумі: права бота, галочки акаунтів, layout, subjects/system, apply → маршрути + топіки), `admin` (`/admin`: users → approve/block, accounts, sync, status; `/sync`, `/sync_full`).
- `__main__.py` — старт без акаунтів, `PyMongoStorage` (`tg_fsm`), команди меню за scope (приват / групи / адміни).
- `callbacks.py`, `keyboards.py`, `texts.py`, `status_text.py` — чисті; `digest.py` — `render(category, label, …)`.

**Тулінг/доки**: venv поза репо (`~/.venvs/wanikani-labs`, правило DEV.md), `pyrightconfig.json` без `venvPath`; `allowed-confusables` у ruff для гліфів кнопок; `deploy/env.example`, runbook §3/§6/§9; `.dev/README.md`, CHANGELOG.

## Перевірено

- `uv run pytest` — 38 тестів (lib 26: crypto, accounts/purge/migrate-keys, users/routes, sync auth-error; bot 12: digest, notifier dry-run/приват/форум з FakeBot/system-fallback, status texts, UI); `ruff check` + `format --check` чисто; `pyright` 0 помилок.
- Локальна база: `migrate-keys --dry-run` → `migrate-keys` за 5.5 с (`main → 07fff792`: history 75 602, events 45 058, assignments 6 453, sync_state 7; `light → 27f9b9f5`: 21 920 / 19 061 / 1 056 / 7); повторно — «nothing to migrate».
- `wklabs accounts add` (токени зі stdin) → `07fff792 Vitalik L39`, `27f9b9f5 2vitalik L7`; `wklabs sync --no-global` — інкремент з місця (135 assignments main, 12 light, 31 подія, 14 запитів), **без baseline** — `sync_state` під новими ключами підхопився.

## Хвости

- Живий Telegram не проганявся (локально `BOT_TOKEN`/`TG_ADMIN_IDS` порожні): хендлери покриті лише тестами чистих частин і Notifier з FakeBot. Твій крок: локально `BOT_TOKEN` + свій id → `/accounts`, `/setup` у тестовому форумі; на vv3 — runbook §9.
- Локальні акаунти без власника (`owner None`): керувати ними через кнопки можуть лише адміни; ти «забереш» їх, надіславши боту той самий токен (revive за `wk_id`) — або `wklabs accounts add --owner <id>`.
- 31 подія з локального sync лежить `notified_at: null`; без маршрутів перший запуск бота позначить їх `skipped`.
- У локальному `.env` лишились `WK_TOKEN__*`, `TG_FORUM_CHAT_ID` — код їх ігнорує; прибрати руками.
- `/setup` від другого користувача в тому ж чаті перезаписує `set_up_by` (чат зникає зі списку «Move all to» першого; маршрути працюють). Deep-link `/start setup_<chat>` не робив — у групі кнопка-лінк у приват.
- Поза v1 (як у плані): шеринг акаунтів, invite-коди/UI-перемикач політики, режими доставки, паралельний sync, ротація `WKLABS_SECRET_KEY` (`MultiFernet`).
