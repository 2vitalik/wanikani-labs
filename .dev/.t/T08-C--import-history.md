# T08 · Імпорт історії з файлів у Mongo: що вже є, прогін локально

`2026-09-10` · 🔆 clarification

Контекст:
- запит у чаті 2026-09-10: «перенести `fetch_smart` з mochi так, щоб писав у Mongo, а не у файли; здається, ми це вже робили в Kanji — взяти звідти ідеї; потім скрипт імпорту даних з файлів у базу, погратися локально, потім деплой»;
- дизайн і фази — [T01](T01-P--architecture-v1.md) (фаза 3 = імпорт історії), рішення — [T02](T02-R--decisions-2026-08-23.md);
- джерела: `mochi/scripts/scrapers/wanikani/fetch_smart.py`, `kanji/importers/wanikani/{fetch.py, once/files_to_db.py, old/v0/*}`, `kanji/db/collections/wk_history.py`; дані — `~/Giga/data/wanikani` (локальний диск, 1.6 GB).

## Що вже є (нічого переносити не треба)

- **`fetch_smart` → Mongo зроблено 2026-08-23 у цьому репо** — `packages/lib/src/wklabs/lib/sync.py` (`SyncEngine`) + `api.py` + `resources.py` + `events.py`. Це надмножина fetch_smart: усі endpoint-и (не лише subjects/assignments/review_statistics), `updated_after` + ETag (1 дешевий запит на endpoint замість повного обходу), rate-limit, `history` (усі версії) і `events` (діфи). Живий прогін є: локальна `wanikani_labs` має 23 840 baseline-версій (4 sync-run-и).
- **Kanji** (2026-03/04) — та сама ідея на крок раніше: `fetch_smart_mongo.py` = fetch_smart з `save_data_mongo` замість файлів; `files_to_db.py` / `migrate_to_mongo.py` — обхід дерева файлів → `wk_*` + `wk_history` (unique `(category, item_id, account, data_updated_at)`, `account=None` для `info`). Локальна Mongo `kanji` — 186k history-доків (часткова міграція). **Усі ці ідеї вже в нашому імпортері** (`importer.py`, написаний 08-23 разом із sync): unique на версію, глобальні subjects без акаунта, дублікати мовчки пропускаються. Брати з Kanji більше нема чого; базу `kanji` можна дропнути, коли наша `history` буде повна.

## Дані на диску

- Дерево `account_<acc>/<type>/<NNxx>/<subject_id>/` — «останнє» (`info|assign|review.json`) + версії `<YYYY-MM>/<cat>__<date>__<time>.json`. **Імʼя файлу = `data_updated_at` обʼєкта, не час фетчу** (так писав `save_data` у mochi); mtime ≈ час фетчу, але ненадійно (файли 2022 переписані 2024-04-22 при реструктуризації) — тому зберігаю його сирим як `history.source_mtime`, а `fetched_at` для імпорту лишається `null`.
- 319 263 json: 286 650 версій (2022: 506 · 2023: 10 130 · 2024: 140 046 · 2025: 121 971 · 2026: 13 997, до 2026-03-28) + 32 613 «останніх» (дублюють останню версію → дублікати за індексом). Типи: radical/kanji/vocabulary/kana_vocabulary; акаунти main/light.
- `mochi/…/_old_data.zip` (590 MB, 37k файлів) — проміжні розкладки квітня 2024 (`data.v1/`, `new_data/`, сирі дампи `data1-04_08`/`04_09`) — той самий період, що вже є в Giga; **не імпортую**.

## Як імпорт лягає в схему

- `wklabs import-files <root>` пише лише `history` (`run_kind=import`, `imported_at`, `source_file`, `source_mtime`); `current`-колекції та `sync_state` не чіпає — живий sync продовжує з місця.
- `wklabs rebuild-events -y` дропає `events` і переграє всю `history` у порядку `(resource, account, resource_id, data_updated_at)`: перша версія обʼєкта — не подія (`first_seen_counts` лише для `incremental`), далі діфи між сусідніми версіями, включно з переходом «остання версія з файлів (03-2026) → baseline (08-2026)» — подія датується `data_updated_at`, тобто реальним часом зміни на боці WK, а не часом фетчу. Усе rebuilt позначається `notified_at` — бот нічого не розсилає.
- Кількість ревʼю між двома версіями стискається в одну подію `reviewed` з `count=max(Δmeaning_correct, Δreading_correct, 1)` — гранулярність = частота старого cron (див. T01, «ключовий наслідок»).

## Що зроблено цієї сесії

- `importer.py`: детермінований (відсортований) обхід, надійний прогрес-лог (кожні 20 батчів), `source_mtime`, warning на не-WK-обʼєкт. Тест `packages/lib/tests/test_importer.py`: синтетичне дерево (2 акаунти, latest-дублікати, битий файл, чужі імена) → лічильники, ідемпотентність, `rebuild-events` дає рівно `srs_up · reviewed · subject_updated` і жодної події на «перше спостереження».
- Реальний прогін у локальну `wanikani_labs` — результати нижче (дописано після прогону).

## Результати локального прогону (2026-09-10, `wanikani_labs`)

- `wklabs import-files ~/Giga/data/wanikani`: 319 263 файли → **172 983 версії**, 146 280 дублікатів, 0 битих, **1:35**. Дублікати зійшлися до одиниці: 32 613 «останніх» файлів + 100 549 info-копій light + 13 118 версій, що збігаються з baseline 08-23 (обʼєкти, не змінені з березня: main — 5 160 assignments і 4 873 review_statistics, subjects — 3 085).
- `history` разом: 196 823 док. (import 172 983 + baseline 23 840); Mongo: ~455 MB даних, ~93 MB на диску, індекси ~72 MB — на vv3 переноситься спокійно.
- `wklabs rebuild-events -y`: **101 271 подія за 7 с**; усі `notified_at` проставлені. По видах: subject_updated 46 245 · reviewed 24 296 · srs_up 21 571 · srs_down 3 400 · passed 2 479 · started 2 365 · burned 906 · subject_hidden 7 · hidden 2. По акаунтах: main 38 210 · light 16 809 · глобальні 46 252. Ревʼю по роках: 2024 — main 7 821 / light 2 917 · 2025 — 6 673 / 2 863 · 2026 — 4 916 / 1 229 (main-2026 стиснуті: 2 793 події на 4 916 ревʼю через діру 03-28 → 08-23).
- Чому нема подій за 2022–2023: до 2024 жоден обʼєкт не має двох версій — це не поллінг, а **перший знімок** кожного обʼєкта з його старим `data_updated_at`. Найраніший `source_mtime` — 2024-04-21 (реструктуризація переписала всі файли; що було до неї — в `_old_data.zip`, теж квітень 2024); 89 % імпортованих версій мають mtime у межах 7 днів від `data_updated_at` — тобто після 2024-04 mtime ≈ час фетчу.
- Чому нема `unlocked`/`level_*`/`user_level`: у файлах ніколи не було assignments з `unlocked_at=null` (WK їх не віддає), а level_progressions/user старий скрапер не збирав — ці види зʼявляться лише з живого sync.
- Аномалія light: 928 з 1 056 assignments мають `data_updated_at` 2026-08-11 (масовий «дотик» WK — схоже на вихід із vacation mode, зсув `available_at`); подій з цього не народилось (жодне поле, яке ми дифимо, не змінилось) — так і має бути.
- Ідемпотентність: повторний прогін дає 0 вставок (перевірено тестом на синтетичному дереві; на реальних даних — не ганяв, нема потреби).

## Далі

- Сервер: за `deploy/README.md` §8 — `mongodump --db wanikani_labs --collection history` локально → `mongorestore` на vv3 → `wklabs rebuild-events -y` там. Деплой бота — окремий крок (чекає токенів).

## Твої думки та питання

> 
