# T37 · Сесії та нотифікації — пілот (сесії, підсумок, карта, картка) — звіт

`2026-09-14` · ⚙️ задача · готово (код), проклацати в Telegram — твій крок

План — [plan.md](plan.md); дизайн — [T32](../T32-P--notifications-model.md), [T33](../T33-P--session-stats-progress.md), [T34](../T34-P--settings-ux-layers.md); поріг — [T31](../T31-C--session-gap-analysis.md).

## Зроблено

**lib**
- `sessions.py` (новий): `split_sessions` (чиста: пауза > gap розриває), `Session`, `SessionRepo` — `ingest` (нові моменти `reviewed`/`started` після `last_at` відкритої сесії або останньої закритої; перша сесія дивиться на 24 год назад; пауза > gap між двома моментами закриває попередню одразу — пізніша подія сама доводить тишу), `close_idle` (лише коли `last_ok_at` поллу ≥ gap після останнього моменту), `close_now` (`⏹`, `closed_by: user`; наступні події відкривають нову), `pending`/`mark_delivered`/`mark_reported` (як `events.delivered`/`notified_at`), `events(session)` (усі події акаунта у вікні ±1 с), `rebuild` (усе з подій, `reported_at` одразу; остання лишається відкритою, якщо ще в межах gap). Ключ **(акаунт, gap)**: індекс `(account, gap, started_at)` unique.
- `stats.py` (новий): `window_stats(events, subjects) -> Stats` — айтеми/відповіді/точність (reading-питання лише для kanji/vocabulary), за типом і рівнем, ⬆️/⬇️ і переходи в групи (guru/master/enlightened/burned), уроки, розблокування, віхи, рівні, тривалість/темп/найдовша пауза, `wrong_items`, `to_doc()` як кеш у `sessions.stats`.
- `progress.py` (новий): `subject_index`, `stage_matrix` (рівень × тип × стадія з `assignments` + `subjects`, `LOCKED = −1`), `reverse_apply` (скасовує `srs_up/down` і `unlocked` вікна → точна матриця «до» без снапшотів), `group_counts`/`total_counts`, `pick_levels` (`around3/5/10/all`), `due_count`, `current_level`, опції `/progress` (`levels · sort · group · filter · style · diff`) з `normalize_options`/`next_option`.
- `notify_settings.py` (замість `route_settings.py`): реєстр v2 — `Setting(key, kind bool|choice|int, default | {kind: default}, label, help, choices, presets, range, kinds, level 1|2, unit)`; L1: `silent · items (live: all, session: wrong) · gap (5·10·15·20·30·45·60) · live`; L2: `min_items (3) · moves · wins · lessons · changes · map · map_levels · map_style`; `for_kind(kind, level)`, `effective` (невалідне ігнорується, `int` з межами), `help_line(kind, level)`.
- `delivery.py`: `Kind`/`KINDS` (`session 🧘 · live 📝 · milestones 🏆 · subjects 📚 · system 🛠` з blurb, scope, словом для гілки, кольором), `Route.kind` (+ читання legacy `category`, `reviews → live`), `Route.title`, `for_kind`, `add_target` = завжди новий маршрут (з копією `settings`), `move_route` копіює налаштування, `move_account` переносить **увімкнені** нотифікації акаунта (не всі види), `ensure_account_routes(kinds=DEFAULT_KINDS)` = `session + milestones`, `reset_settings`, `normalize_legacy`. `db.py`: колекції `sessions`, `reports`, індекси; `_DROP_INDEXES` знімає старий unique `(account, category, chat_id)`. `reports.py` (новий): `Report`/`ReportRepo` — один документ на (route, key), `text_hash`. `accounts.py`: purge/rename охоплюють `sessions`.
- CLI: `wklabs sessions [-a key] [-g 15] [--histogram] [--rebuild] [-n 10]` — гістограма пауз у кошиках T31, сесії за порогом, останні N, перебудова колекції.

**bot**
- `render/common.py` (спільне з `digest.py`: палітра, лінки, `quote` = `<blockquote expandable>`, `chunk`), `render/session.py` (`SessionView` + блоки `header · wrong · all · wins · lessons · changes · map`; live-варіант без важких блоків; важкі блоки відкидаються з кінця, якщо не влазить у 4096), `render/progress.py` (emoji-смуга 10 клітинок за найбільшими остачами, `counts`/`both`, діф справа лише для змінених груп, групування за стадією, фільтри `apprentice`/`changed`, `render_map`).
- `notifier.py`: `notify_sessions()` після кожного sync (з `AppContext.run_sync`): за акаунтом × gap (різні gap на маршрутах = незалежні потоки) → `ingest` → `close_idle` (за `last_ok_at` обох `review_statistics` і `assignments`) → закриті `pending` → фінальний рендер і `send_or_edit` (edit того самого повідомлення через `reports`; якщо його видалили — нове), `min_items` без живого повідомлення → мовчки `delivered`; відкрита сесія з `live: on` → одне повідомлення, edit при кожній зміні (`text_hash` — без порожніх правок). `preview_session(route)` — остання закрита сесія з налаштуваннями маршруту в ціль. Клавіатура `kb_session`: `[⏹ End now] [🗺 Progress]` (після закриття — лише 🗺).
- `handlers/notifications.py` (з `delivery.py`): `📬 Notifications` (види кнопками, види без маршрутів — «→ off», `📚 subjects` по чатах, `➕ Add…`, `➡️ Move all to…`) → вид → маршрут; картка L1 з реєстру (`✅ on · 🔕 Silent · 📄 Items · ⏱ Gap · 📡 Live`) + `⚙️ More…` (L2 з `↩️ Reset to defaults`) + `📍 Change target` + `📨 Preview` (session) / `📨 Send test`; `➕ Add…` → вибір виду з підказкою → той самий picker цілі (`mode add` тепер завжди створює новий маршрут). `handlers/progress.py`: `/progress` у приваті й групі (перший/останній акаунт, `👤` перемикач), кожна кнопка — цикл значення з памʼяттю в `tg_users.prefs.progress[<key>]`, `Δ session` (поточна або остання сесія gap 15) / `day` (з 04:00 у tz бота) / `week` / `off`, `🧹 Close` у групі; `⏹ End now` (власник/адмін → `close_now` + негайний прохід сесій → фінальний edit), `🗺 Progress` (карта з Δ цієї сесії відповіддю в тій самій гілці).
- `routing.py`: `reviews → live`; `topics.py`/`chats.py`/`common.py`/`texts.py`/`keyboards.py`: `kind`; `__main__.py`: `routes.normalize_legacy()` на старті, команда `/progress` у приваті й групах; `users.py`: `TgUser.prefs`, `set_pref`.

## Перевірено

- `uv run pytest` — 71 тест (+11: `split_sessions`, ingest/extend/close/new + два gap, `⏹`/reporting/`reports`, rebuild; `window_stats`; матриця + `reverse_apply` + опції; реєстр v2 і `effective` за видом; legacy `category → kind`; рендер підсумку/live/preview/карти + розміри callback; прохід сесій end-to-end з FakeBot: live send → edit → final edit, `min_items`, preview, видалене живе → нове; dry-run і два gap; `/progress` екран і prefs), `ruff check` + `format --check` чисто, `pyright` 0 помилок. Диспетчер збирається (8 роутерів).
- ⚠️ На **реальних** даних не ганяв: локальна Mongo під `v4u` була зупинена (запуск під `v6u` — Permission denied), тести — на приватному інстансі `:27117` у scratchpad (порт 27017 вільний для твоєї).

## Що перевірити (проклацати)

1. `wklabs rebuild-events` → `wklabs sessions -a 07fff792 --histogram` (цифри ≈ T31 §2–3: 847 сесій при 15 хв) → `wklabs sessions --rebuild` для обох акаунтів (щоб `📨 Preview` і `Δ session` мали що показати; історія не розсилається).
2. Бот локально (окремий тестовий `BOT_TOKEN` або зупинений vv3 — `TelegramConflictError`): при старті в лозі `normalized N legacy route document(s)`; `/accounts → 📬 Notifications`: `📝 Live reviews` і `🏆 Milestones` на місці, `🧘 Session summary → off`.
3. `➕ Add… → 🧘 Session summary → приват` (або форум → `✨ Auto: 🧘 Vitalik · sessions`) → картка з `⏱ Gap: 15 min`, `📡 Live: on`, `📄 Items: wrong only` → `📨 Preview` — підсумок останньої сесії з `❌ wrong`, `🗺 what changed` (розгортається тапом).
4. Зроби кілька ревʼю → після поллу (≤ 5 хв) одне живе повідомлення `· live` з `[⏹ End now] [🗺 Progress]`; ще ревʼю → повідомлення **редагується**, не дублюється; тиша 15 хв + полл → те саме повідомлення стає підсумком (без звуку — Telegram не сповіщає про edit; захочеш звук наприкінці — це `finalize: new` з T34, поки нема). `⏹ End now` — підсумок одразу.
5. `⚙️ More…`: вимкни `🗺 Changes`, увімкни `🗺 Map`, `🎨 Style: both` → `📨 Preview` → порівняй; `↩️ Reset`.
6. `/progress` у приваті: `levels`, `sort`, `group: stage` («концентруюсь на apprentice»), `filter: changed`, `Δ: day`; закрий і відкрий знову — опції збережені; у групі — `🧹 Close`.
7. Другий маршрут `session` у ту саму гілку з `📄 Items: counts only` і `⏱ Gap: 30 min` — два незалежні потоки (перший закриється раніше).

## Хвости (свідомо поза пілотом)

- Затримка кінця = gap + полл 5 хв; адаптивний полл 60 с для відкритих сесій — фаза 5 (T32 §9), `finalize: new` (звук наприкінці), `send_empty`, `compare`/`leeches`, `📉 due до → після` (є лише «зараз»), `⚙️ Defaults` акаунта (`tz`, `day_start`, gap) — зараз `day_start` 04:00 у tz бота, gap лише на маршруті.
- Планові види `hourly/daily/weekly/progress` (T32 §4) і `tick` — фаза 4; `📌 Use in 🧘 Session` з `/progress`; PNG-карта; темплейти/export.
- `PRESET_LABEL` «topic per category» → «topic per kind» (текст), сам ключ `per_category` лишився.
- T35/T36 — повернутись із живим досвідом: список правок після клацання.

## Твої думки та питання

> 
