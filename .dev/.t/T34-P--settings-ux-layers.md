# T34 · UX налаштувань шарами: «клац-клац» за замовчуванням → кроляча нора

`2026-09-13` · 💡 proposal

Контекст:
- твій запит 2026-09-13: за замовчуванням дуже просто — «клац-клац», і мінімально вже працює, нікому не треба заморочуватись; хто хоче — «клік, налаштування, і бац — кроляча нора»: спершу маленький шар (трішки підналаштувати), недостатньо — ще клік, глибше, і так далі; усе через інтерфейс бота; конфіг-файли — лише якщо неминуче; потім, можливо, темплейти й більше влади над тим, що і як відображається;
- є: реєстр `Setting` і картка маршруту з кнопками з реєстру ([T30](T30--chats-v2/report.md)), picker цілі, права `can_edit` ([T26](T26-C--chats-presets-and-rights.md) §5), пресети чату; принципи UX з [T23](T23-P--bot-ux-chats.md): мало команд, один живий екран, діалог лише для тексту, EN;
- модель — [T32](T32-P--notifications-model.md); зміст і опції карти — [T33](T33-P--session-stats-progress.md); варіанти — [T35](T35-B--sessions-alternatives.md) §5.

## 0. Принцип: чотири шари, кожен — один тап углиб

| шар | де | що | для кого |
|---|---|---|---|
| L0 «клац-клац» | після додавання акаунта / `/setup` у чаті | дефолтні нотифікації вже створені; вибір «куди» одним тапом | усі |
| L1 картка | кнопки на картці нотифікації | on/off, silent, 1–2 ключові настройки виду (gap, час, items) | усі |
| L2 More | `⚙️ More…` | блоки on/off, детальність, порівняння, опції карти, finalize, send_empty | хто хоче підкрутити |
| L3 Advanced | `🧪 Advanced…` | порядок блоків, опції блоків, min_items, quiet hours, ✏️ ручний ввід чисел/часу | «погратися» |
| L4 (потім) | `📤 Export` / `📥 Import`, темплейти | JSON нотифікації файлом; текстові темплейти блоків | адвансед |

- Правило: нижчий шар ніколи не потрібен для розумного результату; вищий не ламає нижчий (у всього є дефолт); кожен шар показує лише те, чого нема на попередньому.

## 1. L0 — старт без налаштувань

- Додав акаунт → одразу створюються `🧘 Session summary` і `🏆 Milestones` у приват (T36 Q2); повідомлення після першого sync: `✅ … synced · I'll post a summary here after each study session.` + `[📍 Post elsewhere…] [🌙 Add daily summary] [⚙️ Notifications]`.
- `/setup` у чаті → пресети як зараз; пресет переставляє **увімкнені** нотифікації акаунта (гілки за видом: `🧘 Vitalik · sessions`).
- Більше нічого: перша сесія → перше повідомлення.

## 2. Реєстр налаштувань v2 (`lib/notify_settings.py`)

```
Setting(key, kind: bool | choice | int | time | multi, default | {kind: default},
        label, help, choices=(), presets=(), range=(lo, hi), applies=(kinds…),
        level=1 | 2 | 3, scope=route | account | user, block=None)
```
- `int` на L1 — кнопка-цикл пресетів (`⏱ Gap: 15 min` → 20 → 30 → 45 → 60 → 5 → 10), ручний ввід `✏️` — L3; `time` — цикл (`04:00 · 06:00 · 08:00 · 12:00 · 21:00 · 23:00`) + `✏️`; `multi` — підекран з тумблерами; `block=` — настройка належить блоку, показується на L2 поруч із його тумблером.
- `effective(route, account_settings)` як тепер + `defaults(kind)`; `scope=account` — екран `⚙️ Defaults` акаунта (`tz`, `day_start`, `gap`, дефолтні опції карти); `scope=user` — `tg_users.prefs` (`/progress`).
- Приклад реєстру. L1: `silent` (усі) · `items all|wrong|none` (live, session, daily) · `gap 5…60` (session) · `live on|off` (session) · `at HH:MM` (daily) · `dow + at` (weekly) · `every 1h|2h|3h` (hourly). L2: `blocks` (multi), `detail compact|normal|full`, `compare none|prev|avg7`, `finalize edit|new`, `send_empty`, `map.levels / style / diff / sort / group / filter`, `tone`. L3: `blocks_order`, `min_items`, `quiet_hours`, `max_lines`, `gap` custom.
- Нова настройка = один рядок реєстру + використання в блоці; екрани L1/L2/L3 генеруються з реєстру, як картка в T30. Рядок-підказка внизу екрана — з `help` настройок цього рівня.

## 3. Пресет ↔ кастом

- Вид задає дефолти; у `settings` нотифікації зберігається лише різниця (невалідне ігнорується, як зараз). `↩️ Reset to defaults` на L2.
- Вид не змінюється після створення — замість цього нова нотифікація (`➕ Add…`) і вимкнення старої; так не буває «daily, який поводиться як session».
- «Кастомна» = вид + інші блоки/опції; окремий вид `custom` не потрібен.
- Два акаунти з однаковими налаштуваннями: `📋 Copy settings from…` на L2 — потім, коли справді знадобиться.

## 4. Екрани

### 4.1 Список (заміна `📬 Delivery`)

```
📬 Notifications — Vitalik
🧘 Session → WK forum › 🧘 Vitalik · sessions
🌙 Daily 04:00 → private 🔕
🏆 Milestones → WK forum › 🏆 Vitalik · milestones
📝 Live → off
[🧘 Session] [🌙 Daily] [🏆 Milestones] [📝 Live]
[➕ Add…] [➡️ Move all to…] [⚙️ Defaults] [« Back]
```
- Кнопка виду → список його нотифікацій (цілей), як `kb_category` зараз; вид без нотифікацій → одразу вибір цілі.

### 4.2 `➕ Add…` — вибір виду з підказкою в один рядок

```
What should I post?
[🧘 Session summary — after each study session]
[🌙 Daily summary — every morning: yesterday + progress map]
[📅 Weekly summary — once a week]
[⏱ Hourly digest — every hour, only when you studied]
[🗺 Progress map — levels × SRS, on a schedule or /progress]
[📝 Live reviews — every 5 min, as it happens]
[🏆 Milestones — level-ups, guru, burns]
[« Back]
```
→ picker цілі (є в T30) → картка з `✅ added` зверху. Два кроки — це весь «майстер».

### 4.3 Картка (L1)

```
🧘 Session summary — Vitalik
→ WK forum › 🧘 Vitalik · sessions
[✅ on] [🔕 Silent: off] [📄 Items: wrong]
[⏱ Gap: 15 min] [📡 Live: on]
[⚙️ More…] [📍 Change target] [📨 Preview]
[« 🧘 Session]
gap — minutes of silence that end a session · live — one message updated while you study
```
- `📨 Preview` (замість `Send test` для звітних видів) — рендер **останньої закритої сесії** (для daily — вчорашнього дня) з поточними налаштуваннями в ціль, з позначкою `· preview`. Найшвидший цикл «покрутив — побачив».

### 4.4 `⚙️ More…` (L2)

```
⚙️ Session summary — more
[📊 Moves: on] [❌ Wrong: on] [🏆 Wins: on] [📖 Lessons: on]
[🗺 Changes: on] [🩹 Leeches: off] [📈 Compare: off] [📏 Detail: normal]
[🗺 Map options: 34–39 · emoji · Δ] [🏁 Finalize: edit]
[🧪 Advanced…] [↩️ Reset] [« Card]
```
- Блоки — тумблери; `🗺 Map options` відкриває той самий екран опцій, що `/progress` ([T33](T33-P--session-stats-progress.md) §3.4), з `📌 Use here`.

### 4.5 `🧪 Advanced…` (L3)

- Порядок блоків: список рядків `1 header · 2 moves · 3 wrong …` з кнопками `⬆️` біля кожного (одна кнопка «підняти на одну позицію» — мінімум callback data); `min_items`, `quiet_hours` (`22:00–08:00` → відкласти до ранку), `max_lines`, `✏️ Gap: custom…` (діалог, число).
- Тут же майбутні `📤 Export` / `📥 Import` (§6).

### 4.6 `⚙️ Defaults` акаунта

```
⚙️ Defaults — Vitalik
[🕒 Timezone: Europe/Kyiv] [🌅 Day starts: 04:00] [⏱ Gap: 15 min]
[🗺 Map defaults ▸] [« Back]
```
- Це шар «акаунт» з T07 §4, який досі був порожній; `tz` — перший кандидат ([T22](T22-P--chats-delivery-model.md) §3).

### 4.7 Живе повідомлення сесії

- Клавіатура під ним: `[⏹ End now] [🗺 Progress]`; після закриття — `[🗺 Progress]` лишається (карта на вимогу з цього ж місця), `⏹` зникає.

## 5. Права і чат-сторона

- `can_edit` без змін: власник / адмін бота — усе; адмін чату — on/off, гілка в межах чату, налаштування L1–L3 (він так само може крутити шум у своєму форумі); учасник — своє.
- `🧭 Routes here` → список нотифікацій у чат (вид · акаунт · гілка) → та сама картка.
- Підказка при виборі гілки: «this topic already gets 📝 live for Vitalik» — дублювати свідомо, а не випадково.

## 6. Далі за межами бота (коли стане неминуче)

- `📤 Export` — JSON однієї нотифікації або всіх нотифікацій акаунта файлом у чат; `📥 Import` — відповісти файлом; валідація через реєстр (невідомі ключі ігноруються з попередженням). Це «конфіг-файл» без файлу на сервері і без окремого формату.
- Темплейти: Jinja2 sandbox над `ReportContext` для блоків `header` / `custom` — після стабілізації блоків; autoescape, ліміт довжини, помилка темплейту → дефолтний блок + рядок-попередження.
- CLI-дзеркало для адміна: `wklabs notify list | set <id> <key> <value> | export | import`.

## 7. Callback data

- `nt:<oid>:<action>[:<arg>]` — `card · toggle · set:<key> · more · adv · target · preview · reset · block:<name> · up:<name>` (≤ 40 байт); `pg:<key>:<opt>:<val>` — `/progress`; `ss:<oid>:end` — живе повідомлення. Тест на найдовший лишається.
- Довгі контексти (вибір цілі, ручний ввід) — у FSM, як у T30.

## Твої думки та питання

> 
