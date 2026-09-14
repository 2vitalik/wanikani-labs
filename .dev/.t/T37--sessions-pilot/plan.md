# T37 · Сесії та нотифікації — пілот (сесії, підсумок, карта, картка) — план

`2026-09-14` · ⚙️ задача

Контекст:
- твоє рішення 2026-09-14 (чат, пізно ввечері): не чекати на повні відповіді T36 — зробити **пробну версію за рекомендаціями**, проклацати, і тоді правити; T35/T36 повернуться як список правок після живого досвіду;
- три критичні відповіді (від них залежала модель бази): маршрути `category` → `kind` **без унікальності** (кілька маршрутів одного виду в один чат/гілку — це і є «скільки завгодно режимів»); **режим = маршрут** (налаштування живуть у маршруті; профілі/темплейти — потім); обсяг пілота — сесії + підсумок + карта з діфом + картка налаштувань;
- дизайн — [T32](../T32-P--notifications-model.md) §2–3, §6–8 (фази 1–3 з §9), зміст — [T33](../T33-P--session-stats-progress.md) §1–3, UX — [T34](../T34-P--settings-ux-layers.md) §2, §4.1–4.4; поріг — [T31](../T31-C--session-gap-analysis.md) §4; решта питань T36 — за «рекомендую».

## Уточнення до дизайну (з коду, поки писав)

- Сесії ключуються **(акаунт, gap)**: якщо два маршрути `session` одного акаунта мають різний gap — два незалежні потоки сесій; так «gap на картці» (L1) не суперечить «сесія — сутність акаунта». Індекс `(account, gap, started_at)` унікальний.
- Ідемпотентність підсумків — як у `events`: `sessions.delivered: [route_id]` + `reported_at`; `rebuild-sessions` ставить `reported_at` одразу (історію не шлемо). Живе повідомлення / фінальний edit — через `reports` (`route_id + key = session:<id>` → `message_id`, `text_hash`).
- Закриття: `last_ok_at` поллу `review_statistics` мінус `last_at` сесії ≥ gap (полл упав → чекаємо); `⏹ End now` → `closed_by: user`, наступні події відкривають нову сесію.
- `min_items` (дефолт 3): менша сесія закривається й позначається доставленою без повідомлення; живе повідомлення (якщо було) лишається як є.
- Нові акаунти отримують `session + milestones` у приват; наявні маршрути мігрують `reviews → live` і працюють як були (`normalize_legacy` на старті бота). Гілки пресетів за видом: слово гілки лишається `reviews` для `live`, щоб існуючі гілки збіглися за назвою.
- Реєстр v2 без `time`/`multi` (планові види — не в пілоті); `level 1|2` — картка / `⚙️ More…`; `scope=user` — `tg_users.prefs.progress` для `/progress`.
- Локальна Mongo під `v4u` була зупинена (запуск під `v6u` неможливий) → тести на приватному інстансі `:27117` у scratchpad; перевірка на 2 роках історії (`wklabs sessions --histogram`) — після того, як піднімеш свою Mongo.

## Кроки

**1. lib**
- [ ] `sessions.py`: `split_sessions` (чиста), `Session`, `SessionRepo` (`current · ingest · close_idle · close_now · pending · mark_delivered · list · rebuild`); тести
- [ ] `stats.py`: `window_stats(events, subjects) -> Stats` (T33 §1, без compare/leeches); тести
- [ ] `progress.py`: `stage_matrix`, `reverse_apply`, `due_count`, `changed_items`, групи стадій; тести
- [ ] `notify_settings.py` (заміна `route_settings.py`): `Kind`/`KINDS`, `Setting` v2 (bool/choice/int, level, kinds, дефолт за видом), `for_kind`, `effective`; тести
- [ ] `delivery.py`: `kind` замість `category` (+ legacy read), `normalize_legacy`, `add_target` = завжди новий маршрут, `for_kind`, `DEFAULT_KINDS`; `db.py`: `sessions`, `reports`, індекси, дроп старого унікального; `reports.py`; `rebuild.py`: `rebuild_sessions`
- [ ] CLI: `wklabs sessions [--account] [--gap] [--histogram] [--rebuild] [--last N]`

**2. bot — рендер і доставка**
- [ ] `render/common.py` (спільне з `digest.py`), `render/session.py` (header · moves · wrong · wins · lessons · changes, live-варіант), `render/progress.py` (рядки рівнів, групування за стадією, діф)
- [ ] `notifier.py`: прохід сесій після кожного sync (per акаунт × gap), `send_or_edit` через `reports`, клавіатура живого `[⏹ End now] [🗺 Progress]`; `context.py`: репозиторії, виклик
- [ ] `routing.py`: `reviews → live`

**3. bot — UI**
- [ ] `handlers/notifications.py` (з `delivery.py`): `📬 Notifications` (список за видами) → вид → маршрут; `➕ Add…` → вибір виду → picker цілі; картка L1 з реєстру (`✅ on`, `🔕 Silent`, `📄 Items`, `⏱ Gap`, `📡 Live`) + `⚙️ More…` (L2) + `📨 Preview` (остання закрита сесія); `⏹ End now`
- [ ] `handlers/progress.py`: `/progress` інтерактивний (levels · sort · style · filter · Δ · акаунт), памʼять у `tg_users.prefs`
- [ ] `keyboards.py` / `texts.py` / `callbacks.py` / `__main__.py` (команда, `normalize_legacy`)

**4. Перевірка й доки**
- [ ] `uv run pytest` · ruff · pyright; callback ≤ 64
- [ ] `report.md`, README (стан, наступний крок), CHANGELOG, STATUS
