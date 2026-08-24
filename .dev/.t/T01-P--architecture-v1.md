# T01 · Архітектура v1: монорепо, Mongo-схема, бот-поллер, план запуску

`2026-08-23` · 💡 proposal

Контекст:
- старт проєкту: перенести збір даних WaniKani зі старого cron-скрипта (`mochi/scripts/scrapers/wanikani/fetch_smart.py` → JSON-файли) на Mongo + Telegram-бот, пізніше — веб зі статистикою;
- проміжна спроба `kanji/` (2026-03/04): Mongo-колекції `wk_subjects/wk_assignments/wk_review_stats/wk_history`, pydantic-settings, заглушка TG-нотифікатора — схему «current + history» беремо як прототип;
- сира історія: `~/Giga/data/wanikani` — 1.6 GB, ~286k снапшотів, 2022-11 → 2026-03-28, акаунти `main`/`light` (+`kana_vocabulary`); локальна Mongo `kanji` — 186k history-доків (часткова міграція тих самих файлів). Збір зупинився 28.03.2026 — дірка до запуску не відновлюється;
- живе API (перевірено 2026-08-23): `/reviews` повертає 0 записів — WK прибрав історію окремих ревʼю; працюють `/user`, `/summary`, `/subjects`, `/assignments`, `/review_statistics`, `/level_progressions`, `/study_materials`, `/resets`, `/spaced_repetition_systems`, `/voice_actors`; `updated_after` і ETag працюють; ліміт 60 запитів/хв;
- конвенції з інших проєктів: lang-labs (uv workspace, `src/` + PEP 420 namespace, hatchling, ruff, pyright strict, pytest), nure_msg_bot (aiogram 3 + APScheduler + pydantic-settings, `__main__` → ping Mongo → indexes → polling), vps-infra (systemd + uv без Docker, Mongo 8 native з auth, `/srv/<slug>/{repo,shared,venv}`, бот = long polling без порту; motor застарів → pymongo native async).

## Ключовий наслідок з API

Оскільки `/reviews` порожній, **єдине джерело «що відбулось» — наші діфи `assignments`/`review_statistics` між поллами**. Частота поллу = гранулярність історії ревʼю. Це головний аргумент за частий інкрементальний полл (`updated_after` → 1 запит на endpoint) і за append-only `history`.

## Структура репо

uv-workspace монорепо, один PEP 420 namespace `wklabs`:

```
wanikani-labs/
├─ pyproject.toml      # root-агрегатор: [tool.uv] package=false, workspace members, ruff/pytest
├─ pyrightconfig.json
├─ lib/   → wklabs.lib   settings · db (pymongo async) · api (httpx, ETag, rate-limit)
│                        · sync (full + updated_after) · diff→history→events · render-хелпери
├─ cli/   → wklabs.cli   `wklabs sync [--full] [--account]` · `wklabs status`
│                        · `wklabs import-files <dir>` · `wklabs rebuild-events`
├─ bot/   → wklabs.bot   aiogram 3 + APScheduler (поллер у процесі бота) · топіки форуму
│                        · дайджести · /status /sync
├─ web/   → wklabs.web   FastAPI (фаза 3) · vue/ — Vite+Vue (фаза 3)
├─ scripts/              ops-скрипти (deploy-нотатки, dump/restore)
└─ .dev/
```

- Python `>=3.12` (системний на VPS — без `/opt/uv/python`); dev-група: pytest, pytest-asyncio, ruff, pyright.
- Порти: проєкт **№10** у реєстрі DEV.md → API 8100, Vite 5100 (бот портів не потребує).
- Імена на сервері за словником vps-infra: `/srv/wanikani-labs/`, юзер `app-wanikani-labs`, юніт `wanikani-labs-bot.service` (пізніше `-web`), БД `wanikani_labs` (DB-юзер `readWrite` лише на неї).
- Конфіг — pydantic-settings, `.env` у корені (git-ignored; на VPS — `EnvironmentFile=shared/env`): `BOT_TOKEN`, `TG_FORUM_CHAT_ID`, `TG_ADMIN_IDS`, `MONGO_URI`, `MONGO_DB`, `TZ`, `WK_TOKEN__MAIN`, `WK_TOKEN__LIGHT` (nested delimiter `__` → dict акаунтів), `SYNC_INTERVAL`, `SUBJECTS_INTERVAL`.

## Mongo-схема (БД `wanikani_labs`)

Принцип: **сирий обʼєкт API зберігається незмінним** (`data` = як прийшло, рядкові таймстемпи з мікросекундами), зверху — підняті типізовані поля для індексів/запитів (BSON date). Будь-яка пізніша аналітика перераховується з raw.

Колекції поточного стану (спільний конверт `_id`=id з WK · `account` (null для глобальних) · `object` · `url` · `updated_at` (date) · `fetched_at` · `data` raw):
- `subjects` — глобальні; підняті `type`, `level`, `slug`, `characters`, `hidden_at`;
- `assignments` — `subject_id`, `subject_type`, `srs_stage`, `available_at`, `unlocked_at`, `started_at`, `passed_at`, `burned_at`, `hidden`; unique `(account, subject_id)`;
- `review_statistics` — `subject_id`, `subject_type`, `percentage_correct`, `meaning_correct/incorrect`, `reading_correct/incorrect`;
- `level_progressions`, `study_materials`, `resets` — аналогічно;
- `users` — `_id` = ключ акаунта, `data` = `/user`, `level`;
- `summaries` — знімки `/summary` per `(account, data_updated_at)` (≈24/добу/акаунт, для графіків «доступних ревʼю»);
- `srs_systems`, `voice_actors` — глобальні довідники.

Історія та похідне:
- `history` — append-only всі версії всіх ресурсів: `resource, account, resource_id, data_updated_at (str), updated_at (date), fetched_at, doc` (повний обʼєкт WK); unique `(resource, account, resource_id, data_updated_at)`. Прямий нащадок `wk_history`; сюди ж лягає імпорт із Giga.
- `events` — похідний потік подій: `account, resource, resource_id, subject_id, kind, at, fetched_at, prev, cur, delta, history_id, notified_at`. Види v1: `unlocked · started · srs_up · srs_down · passed · burned · resurrected · reviewed (Δ✓/Δ✗ з лічильників review_statistics) · level_started · level_passed · level_completed · user_level · subject_new · subject_updated · subject_hidden · reset`. **Повністю перебудовується з `history`** (`wklabs rebuild-events`) — це страховка від будь-яких майбутніх змін таксономії.
- `sync_state` — `_id`=`account:endpoint`: `updated_after`, `etag`, `last_run_at`, `last_ok_at`.
- `sync_runs` — журнал поллів (лічильники fetched/new/changed на endpoint, помилки) — основа `/status` і heartbeat.
- `tg_topics` — `_id` = логічне імʼя топіка → `chat_id`, `thread_id` (бот створює сам); `tg_messages` — що відправлено (ідемпотентність після рестартів).

## Бот і поллер

- Один процес: aiogram 3 (polling) + APScheduler `AsyncIOScheduler` (in-memory jobstore; job `sync` інтервальний, `coalesce`, `max_instances=1`; `subjects` — щогодини). Порядок старту як у nure_msg_bot: ping Mongo → indexes → Bot/Dispatcher → scheduler → polling; `Restart=always` у systemd.
- Перший повний sync = **baseline без сповіщень** (події позначаються `baseline`), далі сповіщення лише про діфи.
- Сповіщення — **один дайджест на полл на акаунт на топік**, не повідомлення на подію: `37 reviews ✅31 ❌6 · ⬆️12 ⬇️4 · Guru +3 · 🔥 +1` + список айтемів (обрізається, «…+N»).
- Топіки (бот створює при старті, якщо нема; `can_manage_topics`): `main · reviews`, `main · milestones`, `light · reviews`, `light · milestones`, `subjects` (зміни контенту WK), `system` (помилки, stalled-sync, heartbeat). Маршрутизація `kind → topic` — таблиця в `wklabs.bot.routing`, міняється без зміни схеми.
- Команди v1 (тільки `TG_ADMIN_IDS`): `/status` (останній sync, лічильники, рівні, доступні ревʼю з `/summary`), `/sync` (примусовий полл).
- Без токена бота — dry-run: дайджести в лог (для розробки).

## Фази

1. **Каркас + v1** (ця сесія): lib → cli `sync` → bot → тести на локальній Mongo (`wanikani_labs_test`).
2. **VPS**: юзер/БД/юніт за `vps-infra/steps/80_site.md` + бот-юніт із T20; перший full sync; перевірка сповіщень.
3. **Імпорт історії**: `wklabs import-files ~/Giga/data/wanikani` → `history` (локально, потім `mongodump`/`mongorestore` на VPS — або rsync файлів і імпорт там), `rebuild-events`. Ідемпотентно — можна будь-коли.
4. **Web**: FastAPI + Vue (статистика, графіки SRS/рівнів/точності), порти 8100/5100.
5. Далі: денний дайджест, нагадування «доступні ревʼю», стати за періодами.

## Відкладене / відкрите

- APScheduler 3.x vs 4 — 3.11 (стабільний, є в nure_msg_bot).
- Чи зберігати `summaries` щопоток — так, дешево; якщо роздує — TTL.
- Зовнішній моніторинг (healthchecks.io dead-man's switch) — після запуску.

## Твої думки та питання

> 
