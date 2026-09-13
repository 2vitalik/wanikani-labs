# T32 · Нотифікації як сутність: тригер × зміст × ціль, сесії, звіти, розклад, код

`2026-09-13` · 💡 proposal

Контекст:
- твій запит 2026-09-13 (голосом, переказ): бот має ловити кінець заняття і слати підсумок сесії (скільки уроків і які, ревʼю, помилки, успіхи); поріг паузи налаштовується; «раз на годину / раз на якийсь час» лишити опцією; нотифікацій — **скільки завгодно** з різними комбінаціями для різних гілок і чатів (це інша концепція, ніж «увімкнути/вимкнути» в T30); налаштування спочатку прості (що показувати, як), потім — темплейти й більше влади; за замовчуванням «клац-клац», глибше — кроляча нора; через бота, конфіг-файли — лише якщо неминуче; мотивація — бачити прогрес і зміни одразу;
- бачення — [T07](T07-P--bot-vision.md) §1 (сесії, денний підсумок, стрік), §6 (статистика à la wkstats), §7 (оформлення); чати й маршрути — [T22](T22-P--chats-delivery-model.md), [T26](T26-C--chats-presets-and-rights.md), реалізовано в [T29](T29--chats-v1/report.md)/[T30](T30--chats-v2/report.md) (`tg_routes`, реєстр `Setting`, `effective`, picker цілі, `can_edit`);
- емпірика межі сесії — [T31](T31-C--session-gap-analysis.md); зміст повідомлень і карта — [T33](T33-P--session-stats-progress.md); UX налаштувань — [T34](T34-P--settings-ux-layers.md); варіанти з аргументами — [T35](T35-B--sessions-alternatives.md); питання — [T36](T36-Q--sessions-questions.md).

## 0. Суть одним абзацом

Маршрут (T22) був «категорія подій → ціль». Стає **нотифікація = вид × ціль × налаштування**, де вид = пресет (тригер + набір блоків + дефолти): живий дайджест, підсумок сесії, денний, тижневий, погодинний, віхи, карта прогресу, предмети, система. Нотифікацій одного виду — скільки завгодно, на будь-які цілі (той самий чат, різні гілки), кожна зі своїми налаштуваннями. Сесія — похідна сутність з `events` (пауза між моментами ≥ gap), звіти — ідемпотентні через колекцію `reports`. Усе з T30 лишається (`tg_routes`, пресети чату, права, picker): `category` стає `kind` з більшою кількістю значень, а Notifier отримує два нові проходи — сесійний і плановий.

## 1. Види нотифікацій

| вид | тригер | зміст за замовчуванням | scope |
|---|---|---|---|
| 📝 `live` (= нинішній `reviews`) | кожен полл з подіями | ревʼю/уроки/переходи, як зараз | акаунт |
| 🏆 `milestones` | кожен полл | рівні, guru/burn, ресети (як зараз) | акаунт |
| 🧘 `session` | закриття сесії (тиша ≥ gap) + живе повідомлення під час | підсумок сесії ([T33](T33-P--session-stats-progress.md) §1–2) | акаунт |
| ⏱ `hourly` | раз на годину, лише якщо були події | підсумок вікна | акаунт |
| 🌙 `daily` | щодня о HH:MM (дефолт 04:00 — межа доби) | підсумок доби + карта прогресу з діфом за добу | акаунт |
| 📅 `weekly` | раз на тиждень | підсумок тижня + карта | акаунт |
| 🗺 `progress` | за розкладом (день/тиждень) або на вимогу `/progress` | лише карта рівнів (T33 §3) | акаунт |
| 📚 `subjects` · 🛠 `system` | як зараз | як зараз | глобальні |

- Вид = пресет: визначає тригер, порядок блоків і дефолти налаштувань. «Кастомна» нотифікація = будь-який вид зі зміненими блоками (T34 §3); окремого виду `custom` не треба.
- Один вид — багато разів: «сесія з айтемами → гілка A» + «сесія лише лічильники → гілка B» = дві нотифікації виду `session` з різним `items`. Це і є «різні комбінації для різних гілок».
- `hourly` — твій «раз на годину»: лишається як звичайний плановий вид (§4), окремого коду не потребує.

## 2. Сесія — похідна сутність

- Визначення: моменти `at` подій `reviewed` і `started` акаунта; ланцюжок, у якому сусідні моменти різняться ≤ `gap` (дефолт 15 хв — [T31](T31-C--session-gap-analysis.md) §4). Склад сесії — **усі** події акаунта з `at ∈ [start − 1 с, end + 1 с]` (переходи SRS, віхи, розблокування мають ті самі секунди, T31 §1).
- Чиста функція `split_sessions(instants, gap) -> [(start, end, n)]` — та сама для live і для `rebuild`; правила можна міняти заднім числом (правило проєкту).
- Стан `open`, поки не підтверджено тишу; **закриття — лише за фактом успішного поллу**: `sync_state[account:review_statistics].last_ok_at − last_at ≥ gap`. Полл упав → сесія чекає (по годиннику не закриваємо, бо не знаємо, що сталось); полл після простою знайшов дві сесії → `split_sessions` розділить сам.
- Ручне закриття: `⏹ End now` на живому повідомленні → `closed_by: user`; події в межах gap після цього відкривають нову сесію (просте правило; reopen — [T35](T35-B--sessions-alternatives.md) §1).
- Колекція `sessions` (похідна, `wklabs rebuild-sessions` перебудовує з `events`): `{_id, account, started_at, ended_at (останній момент), last_at, status open|closed, closed_at, closed_by auto|user, gap, n_instants, kind reviews|lessons|mixed, stats (кеш T33 §1), due_open, due_close}`; індекси `(account, started_at)`, `(status)`. `due_*` — спостережене на момент відкриття/закриття (з `assignments`), при rebuild — з версій `summary` в `history` або порожньо; так і позначається.
- Лише уроки (`started` без `reviewed`) — теж сесія (`kind: lessons`), підсумок адаптується.
- Два акаунти однієї людини — дві незалежні сесії; спільна нотифікація «обидва в одне повідомлення» — не зараз (T35 §4).

## 3. Життєвий цикл повідомлень

- **Live (`live: on`, пропоную дефолт on):** перший полл, що побачив події сесії → одне повідомлення `🧘 Vitalik · session 17:52 → … · live · 12 reviews · ✅ 10 ❌ 2`; кожен наступний полл → `edit_message_text` того самого повідомлення (редагування **не сповіщає** — нуль спаму). Закриття → фінальний edit з повним підсумком. Обмеження часу на редагування власних повідомлень у ботів немає.
- `finalize: edit | new` (дефолт `edit`): `new` — на закритті додатково коротке повідомлення-відповідь на живе (для тих, кому потрібен звук саме в кінці).
- **`live: off`** — одне повідомлення на закритті.
- Затримка кінця: gap + інтервал поллу (15–20 хв) → **адаптивний полл**: акаунт із відкритою сесією опитується щохвилини лише по `assignments`, `review_statistics`, `summary` (3 запити/хв на токен, ліміт 60) — `SyncEngine.run(accounts=[…], resources=[…])` це вже вміє; окрема job `sync_active` кожні 60 с (фаза 2, T36 Q6).
- Ідемпотентність: колекція `reports` `{route_id, kind, key, chat_id, thread_id, message_ids, sent_at, updated_at, final: bool, text_hash}`; `key` = `session:<session_id>` для сесій, `window:<start_iso>` для планових. Рестарт посеред → звіт знаходиться за ключем і **редагується**, а не шлеться вдруге; `text_hash` — не редагувати, якщо текст не змінився. Це узагальнення `events.delivered` для не-миттєвих видів; миттєві лишаються на `delivered`/`notified_at`.

## 4. Планові види (`hourly · daily · weekly · progress`)

- Одна job `tick` щохвилини: `routes.find({kind ∈ scheduled, enabled, next_run_at ≤ now})` → вікно `[last_window_end, now)` (для `daily` — `[day_start учора, day_start сьогодні)` у tz акаунта) → рендер → `reports` → `next_run_at` за `schedule`. Стан у документі маршруту, не в APScheduler → переживає рестарт, працює для будь-якої кількості користувачів, пропуск під час простою = просто надішле при старті.
- `schedule` за видом: `hourly` — `{every: 1h|2h|3h}`; `daily` — `{at: "04:00"}`; `weekly` — `{dow: mon, at: "09:00"}`; `progress` — `daily | weekly | off` (лише `/progress` на вимогу).
- Порожнє вікно: `send_empty` (дефолт off) — мовчати; on — «no activity yesterday» (для дисципліни/стріків, T07 §1).
- Межа доби `day_start` (дефолт 04:00, шар акаунта): сесія належить добі, в якій **почалась**; денний звіт о `day_start` включає нічне заняття.
- Сесія, що триває в момент `tick` денного звіту, — у завтрашній звіт цілком (без розрізання).

## 5. Що бачить кожен вид з подій

`routing.py` сьогодні: `kind_of_event → category`. Стає `interest(notification_kind) -> set[event_kind]`:
- `live`: reviewed · srs_up · srs_down · unlocked · started;
- `milestones`: passed · burned · resurrected · level_* · user_level · reset;
- `session · hourly · daily · weekly`: усі акаунтні події вікна (ревʼю + віхи + уроки);
- `progress`: подій не потребує; стан + діф (T33 §3), події лише для «що змінилось»;
- `subjects` / `system`: як зараз.
- Подія може піти в кілька нотифікацій (live і session) — це нормально, це різні цілі. Обидва види в одну й ту саму гілку — вибір користувача; UI при виборі гілки попереджає одним рядком («this topic already gets 📝 live for Vitalik»).

## 6. Зміни моделі й міграція

- `tg_routes`: `category` → **`kind`** (`reviews` → `live`, решта як є) — `normalize_legacy` на старті, як для чатів у T29; `+ schedule {…}`, `+ next_run_at`, `+ last_window_end`, `+ last_run_at`.
- Унікальний індекс `(account, category, chat_id)` знімаємо: потрібні ≥ 2 нотифікації одного виду в одному чаті (різні гілки або налаштування). `upsert(account, kind, chat)` лишається як «перша нотифікація такого виду в чаті або створити» (пресети чату, `subscribe` глобальних); `add_target` завжди створює нову. Індекси: `(account, kind, chat_id)` неунікальний, `(kind, enabled, next_run_at)`.
- Пресети форуму (`per_category` тощо) створюють гілки за **видом**: `🧘 Vitalik · sessions`, `🌙 Vitalik · daily`; `topic_title(kind, label)`, `CATEGORY_ICON/COLOR` → `KIND_ICON/COLOR`; пресет застосовується до увімкнених нотифікацій акаунта, не до всіх видів.
- Реєстр `Setting` (T30) розширюється: `kinds` замість `categories`, `level 1|2|3`, типи `int`, `time`, `multi`, `scope route|account` — [T34](T34-P--settings-ux-layers.md) §2. Файл `route_settings.py` → `notify_settings.py`.
- Дефолти нового акаунта: замість `live + milestones → приват` пропоную **`session + milestones → приват`** (`daily` — одним тапом); твої наявні маршрути мігрують як `live` і працюють як були — T36 Q2.
- `events` без змін. Нові колекції `sessions`, `reports`; `tg_users.prefs` — особисті опції `/progress` (T33 §3.4).

## 7. Notifier: три проходи після кожного sync

1. **instant** — як сьогодні (`notify_pending`), лише для `live · milestones · subjects · system`.
2. **sessions** — `SessionTracker.ingest(account, events_of_run)` → open/extend; для відкритих сесій з нотифікаціями `session` (`live: on`) → рендер → send або edit за `reports`; `close_idle()` за правилом §2 → фінальний рендер/edit (+ `new`, якщо задано), `sessions.stats` кешується на закритті; `min_items` менше порога → без окремого повідомлення (живе, якщо було, лишається як є).
3. **scheduled** — той самий `tick` (§4), викликаний тут, щоб не чекати хвилину.
- Рендер — чисті функції над `ReportContext` (T33 §4); Notifier лише обирає ціль, `silent`, edit vs send, і пише `reports`.

## 8. Код (по файлах)

`lib` (чисте, над Mongo):
- `sessions.py` — `split_sessions` (чиста), `Session`, `SessionRepo` (`open · extend · close · current(account) · list(account, since) · rebuild`), `should_close(session, last_ok_at, gap)`.
- `stats.py` — `window_stats(events, subjects) -> Stats` (T33 §1): чиста; сесії, daily/weekly, `/status`, майбутній web рахують одним кодом (T07 §6).
- `progress.py` — `stage_matrix(db, account)`, `reverse_apply(matrix, events)`, `due_count(db, account, at)`, `changed_items(events)` (T33 §3).
- `notify_settings.py` (заміна `route_settings.py`) — реєстр v2, `KINDS`, `interest()`, `defaults(kind)`, `effective()`.
- `delivery.py` — `Route.kind`, `schedule`, `next_run_at`; `RouteRepo.due_scheduled(now)`, `mark_run(route, window_end)`, `normalize_legacy`; `reports.py` — `Report`, `ReportRepo` (`get(route, key)`, `upsert`).
- CLI: `wklabs sessions [--account] [--gap N] [--histogram] [--rebuild]` — перевірка на 2 роках історії до будь-якого UI; `wklabs report session --last [--account]` — рендер у stdout для дебагу текстів.

`bot`:
- `render/` пакет замість `digest.py`: `blocks.py` (кожен блок — функція), `report.py` (компоновка за `blocks`, chunking), `progress.py` (карта); `digest.py` лишається для `live`/`subjects`.
- `notifier.py` — три проходи §7; `send_or_edit(route, key, texts, *, final)`; `scheduler.py` — `tick` (60 с), `sync_active` (адаптивний, фаза 2).
- `handlers/notifications.py` (з `delivery.py`): список за видами, `➕ Add…` (вид → ціль), картка з рівнями налаштувань (T34 §4), `⚙️ Defaults` акаунта; `handlers/progress.py` — `/progress` інтерактивний (T33 §3.4); `⏹ End now` на живому.
- `texts.py`/`keyboards.py` — нові екрани; callback data `nt:<oid>:<action>[:<arg>]`, `pg:<key>:<opt>:<val>`, `ss:<oid>:end` — тест ≤ 64 байт лишається.

Тести: `split_sessions` (таблиця: одна, дві, gap рівно на межі, лише уроки, порожньо, події з простою); `should_close` (полл упав / успішний / рівно gap); `window_stats` на побудованих подіях (точність по айтемах і відповідях, типи, переходи); `reverse_apply` (матриця до/після на серії подій, звірка з реплеєм `history` на тестових даних); рендер блоків детермінований; Notifier: live send → edit → final, рестарт посеред (`reports`), `min_items`; scheduled: вікна, `next_run_at`, `send_empty`; `normalize_legacy` маршрутів; callback ≤ 64.

## 9. Порядок реалізації (кожна фаза лишає бота робочим)

1. **Сесії в lib + CLI** (~M): `sessions.py`, `stats.py`, `rebuild-sessions`, `wklabs sessions --histogram` — дивимось на 2 роки історії, що межі й статистика правильні, ще до UI; тут же `rebuild-events` локально (T31 §6).
2. **Вид `session` у боті** (~M): міграція `kind`, `reports`, прохід сесій у Notifier, live/edit/final, рендер підсумку (T33 §1–2) з блоком «що змінилось» за сесію, картка з L1 (`gap`, `live`, `silent`, `items`), `➕ Add… → 🧘 Session`, дефолти нового акаунта, `⏹ End now`.
3. **Карта прогресу** (~M): `progress.py`, `/progress` інтерактивний з памʼяттю опцій, блок `changes`/`map` у session.
4. **Планові види** (~S–M): `tick`, `daily/weekly/hourly/progress` за розкладом, `day_start`, `send_empty`.
5. **Кроляча нора L2/L3** (~M): блоки, детальність, порівняння, порядок блоків, `📨 Preview` на реальній останній сесії; адаптивний полл.
6. Потім: PNG-карта (Pillow), темплейти / export-import (T34 §6), стріки, спільна нотифікація двох акаунтів.

Після відповідей у [T36](T36-Q--sessions-questions.md) — задача-тека з планом на фази 1–2.

## 10. Ризики й межі

- Затримка кінця сесії (gap + полл) неминуча за визначенням «тиша»; компенсується live, адаптивним поллом і `⏹ End now`.
- Edit живого повідомлення — 1 виклик API на полл на відкриту сесію — дрібниця; але Telegram не сповіщає про edit, тому фінал за замовчуванням тихий (T36 Q3).
- Після зміни `gap` або `rebuild-sessions` id сесій змінюються → `reports` для них старі; rebuild позначає перебудовані сесії `reported: true` (як `rebuild-events` ставить `notified_at`) — повторно не шлемо.
- Один `BOT_TOKEN` у двох процесах (локально + vv3) — `TelegramConflictError`, як і раніше; локальний прогін сесій — з окремим тестовим ботом або в dry-run (`reports` пишуться і в dry-run, без `message_ids`).
- Карта обмежена `max_level_granted`; `hidden` предмети не рахуються.

## Твої думки та питання

> 
