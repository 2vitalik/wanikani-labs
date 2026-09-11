# T18 · Акаунти v1: users/accounts/chats/routes + UI бота — план

`2026-09-11` · ⚙️ задача

Контекст:
- дизайн — [T14](../T14-P--accounts-model.md), UX — [T15](../T15-P--bot-ux-accounts.md), рішення — [T17](../T17-Q--accounts-questions.md) (старт — після ⭐-відповідей);
- один великий шматок, але шарами: спершу `lib` (тестується без Telegram), потім доставка, потім UI; кожен крок лишає бота робочим.

## Кроки

**1. lib — дані й безпека**
- [ ] `settings.py`: `secret_key`, `access_policy`; `deploy/env.example` + runbook §3 (`wklabs gen-key`)
- [ ] `crypto.py` (`cryptography` у `wklabs-lib`), тест roundtrip
- [ ] `db.py`: колекції `accounts · tg_users · chats · routes`, індекси; `tg_topics` — новий `_id`
- [ ] `accounts.py`: `Account`, `AccountRepo`, `validate_token`, `key_for`, `purge`; тести (create / dup / revive / auth_error / purge не чіпає глобальне)
- [ ] `users.py`, `delivery.py` (`ChatRepo`, `RouteRepo`, `default_routes`), тести
- [ ] `sync.py`: клієнти з репо, 401 → `auth_error`, no-op без акаунтів, `from_tokens` для тестів; `test_sync.py` зелений
- [ ] `status.py` — від списку акаунтів
- [ ] `bootstrap.py` (env → accounts, forum → chat + routes, legacy `tg_topics`), тест ідемпотентності
- [ ] CLI: `accounts list / add / import-env / pause / resume / remove / purge`, `gen-key`; `sync -a` через репо

**2. bot — доставка за маршрутами**
- [ ] `routing.py` → `category_for`; `topics.py` → `ensure_topic / rename`; `notifier.py` → маршрути, `delivered`, `skipped` без маршрутів; `digest.py` — `label` у заголовках
- [ ] `context.py`, `__main__.py`: bootstrap, старт без акаунтів, scope-и команд
- [ ] тести notifier: приват (`thread_id = null`) + форум (топік створюється) + вимкнений маршрут

**3. bot — користувачі й UI**
- [ ] `middleware.py` (`tg_users` upsert, pending / blocked), `filters.py`, `callbacks.py`, `keyboards.py`, `texts.py`
- [ ] `handlers/start.py` (онбординг, approve-запит, deep-link), `handlers/admin.py` (approve / block, users, accounts, sync)
- [ ] `handlers/accounts.py`: список, картка, add (FSM, видалення повідомлення, валідація, перший sync), rename, replace token, pause / resume, remove
- [ ] `handlers/setup.py`: `/setup` у групі/форумі, права бота, галочки, apply → топіки + маршрути; повторний `/setup` = редагування
- [ ] delivery-картка: on / off, move
- [ ] `/status` — свої акаунти; `/help`

**4. Перевірка й деплой**
- [ ] `uv run pytest` · ruff · pyright
- [ ] локально з реальним Telegram: `/start` → add `light` токеном → приват-дайджест; `/setup` у тестовому форумі → топіки; bootstrap з `.env` на чистій базі
- [ ] `.dev/README.md` (конвенції + стан), CHANGELOG, runbook (`WKLABS_SECRET_KEY`, bootstrap, `WK_TOKEN__*` необовʼязкові)
- [ ] vv3: `shared/env` + ключ → редеплой → лог `imported main/light from env` → `/accounts` у приваті

Хвости поза v1 (окремі тікети, коли дійде): шеринг акаунтів (`viewer`); invite-коди / UI-перемикач політики; режими доставки (session / daily — крок 2 [T07](../T07-P--bot-vision.md)); паралельний sync по акаунтах (> 50 акаунтів); ротація `secret_key`.
