# wanikani-labs

Збір усіх даних з WaniKani API у MongoDB (поточний стан + повна історія версій + похідні події), Telegram-бот зі сповіщеннями у форум-топіки, пізніше — веб зі статистикою. Дизайн і рішення — у [`.dev/`](.dev/README.md) (тікет [T01](.dev/.t/T01-P--architecture-v1.md)).

| Підпроєкт | Пакет | Що |
|---|---|---|
| `lib/` | `wklabs.lib` | settings · Mongo (PyMongo async) · WaniKani API client · sync engine · events · importer |
| `cli/` | `wklabs.cli` → `wklabs` | `sync` · `status` · `import-files` · `rebuild-events` · `accounts` |
| `bot/` | `wklabs.bot` → `wklabs-bot` | aiogram 3 + APScheduler (поллер у процесі) · топіки форуму · дайджести · `/status` `/sync` |
| `web/` | `wklabs.web` → `wklabs-web` | FastAPI (`/api/health`, `/api/status`), порт **8100**; `vue/` — фаза 3 (порт 5100) |

## Швидкий старт (локально)

```bash
uv sync                         # venv + усі підпроєкти (editable)
cp .env.example .env            # WK_TOKEN__MAIN=…, WK_TOKEN__LIGHT=…, (BOT_TOKEN, TG_FORUM_CHAT_ID, TG_ADMIN_IDS)
uv run wklabs accounts          # що сконфігуровано
uv run wklabs sync              # перший запуск = baseline (~20 с, ~50 запитів); далі — інкрементально (~3 с)
uv run wklabs status
uv run wklabs-bot               # без BOT_TOKEN — dry-run: поллить, дайджести пише в лог

uv run pytest                   # потребує локальної Mongo (БД wanikani_labs_test)
uv run ruff check . && uv run ruff format --check . && uv run pyright
```

## Як це працює

- **Polling.** Кожні `SYNC_INTERVAL` с (5 хв) по кожному акаунту: `user`, `summary`, `level_progressions`, `assignments`, `review_statistics`, `study_materials`, `resets` — з `updated_after` (1 дешевий запит на endpoint; `user`/`summary` — через ETag). Раз на `SUBJECTS_INTERVAL` (год) — глобальні `subjects`, `spaced_repetition_systems`, `voice_actors`.
- **Зберігання.** Сирий обʼєкт API — незмінним у полі `item`; зверху підняті типізовані поля для індексів. Колекції поточного стану по ресурсу + `history` (append-only всі версії, unique на `(resource, account, resource_id, data_updated_at)`) + `events` (похідні: `reviewed`, `srs_up/down`, `unlocked`, `started`, `passed`, `burned`, `level_*`, `subject_updated`…; перебудовуються з `history` командою `rebuild-events`).
- **Baseline.** Перший sync акаунта/ресурсу лише записує версії — подій і сповіщень нема. Далі кожен полл → події → **один дайджест на акаунт на топік**.
- **Топіки форуму** (бот створює сам, памʼятає в `tg_topics`): `📝 <acc> · reviews`, `🏆 <acc> · milestones`, `📚 subjects`, `🛠 system`. Маршрутизація подій — `bot/src/wklabs/bot/routing.py`.
- **Історія 2022–2026** зі старого файлового скрапера: `uv run wklabs import-files ~/Giga/data/wanikani` → `history`, потім `uv run wklabs rebuild-events`.

## Сервер (vv3)

Натівний systemd + uv, без Docker — за конвенціями `vps-infra`: `/srv/wanikani-labs/{repo,shared,venv}`, юзер `app-wanikani-labs`, БД `wanikani_labs`, юніт `wanikani-labs-bot.service`. Покроково — [deploy/README.md](deploy/README.md).
