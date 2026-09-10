# wanikani-labs — робоча памʼять проєкту

Мета: збирати **все**, що дає WaniKani API, у MongoDB — поточний стан, повну історію версій і похідні події (ревʼю, SRS-переходи, рівні, зміни контенту) — і жити з цим далі: Telegram-бот із дайджестами у форум-топіки (зараз), веб зі статистикою (фаза 3). Продовження старого cron-скрапера (`mochi/`, файли 2022–2026) і проміжної спроби `kanji/`.

Метод — жива спека: `/Users/v4u/Dropbox/v4/Dev/My/dev-md-rules/APPROACH.md` (компактний шар DEV.md — у кожній сесії). Реєстр тікетів — [MAP.md](MAP.md), дерево вузлів — [TREE.md](TREE.md), журнал — [CHANGELOG.md](CHANGELOG.md), голос проєкту — [STATUS.md](STATUS.md).

Бачення бота (фон, не план) — [T07](.t/T07-P--bot-vision.md): сесії / денні підсумки / стріки, сповіщення про контент, нагадування, ревʼю й уроки через бота, статистика à la wkstats, multi-account / multi-user; там же — пропозиція черговості кроків.

## Конвенції

- Репо = uv-workspace монорепо, namespace `wklabs`; підпроєкти — під `packages/` ([T03](.t/T03-C--packages-layout.md)): `lib/` (ядро) · `cli/` (`wklabs`) · `bot/` (`wklabs-bot`) · `web/` (`wklabs-web`, порт 8100) · `vue/` (фаза 3, порт 5100); поза пакетами — `deploy/` (юніт, env-шаблон, runbook), `scripts/`. Дизайн і чому саме так: [T01](.t/T01-P--architecture-v1.md) (дерево там — до T03), стартові рішення: [T02](.t/T02-R--decisions-2026-08-23.md).
- Код/ідентифікатори/коментарі — EN; документація й спілкування — UA.
- Коміти робить лише Vitalik (агент — на явне прохання). Формат — глобальна конвенція (`# git` у `/Users/Shared/.claude/CLAUDE.md`): `<type>[(scope)]: <summary>, tNN[-MM][,KK]`, заголовок ≤ 72, деталі списком у тілі, у суфіксі лише тікети, які коміт створює/змінює — пропозиція [T04](.t/T04-P--commit-convention.md), рішення [T06](.t/T06-R--commit-convention-answers.md).
- Стек: Python ≥3.12, PyMongo native async (не motor), httpx, pydantic-settings, aiogram 3, APScheduler 3, typer, FastAPI; ruff + pyright + pytest (тести — на реальній локальній Mongo, БД `wanikani_labs_test`).
- Секрети — `.env` (git-ignored) локально, `shared/env` на сервері; шлях до файлу — `WKLABS_ENV_FILE`, дефолт `.env` у корені репо незалежно від cwd (як `NURE_ENV_FILE` у nure-students); акаунти WK — `WK_TOKEN__<KEY>`.
- Проєкт №10 у реєстрі портів DEV.md.

## Вузли

Поки всі тікети в корені `.t/`; вузли зʼявляться, коли наросте (кандидати: `lib/` схема й sync, `bot/` сповіщення, `web/`).

## Стан

- ✅ v1 зібрано й перевірено локально: baseline-sync обох акаунтів (23 840 обʼєктів, 18 с, 52 запити), інкрементальний — 3 с; бот у dry-run поллить; 14 тестів, ruff/pyright чисті.
- ⬜ Деплой на vv3 — [deploy/README.md](../deploy/README.md); потрібні від тебе `BOT_TOKEN`, `TG_FORUM_CHAT_ID`, `TG_ADMIN_IDS`.
- ✅ Історія з файлів імпортована локально й звірена до одиниці ([T08](.t/T08-C--import-history.md)): 319 263 файли → 172 983 версії за 1.5 хв, `rebuild-events` → 101 271 подія за 7 с (після zip — 109 285); `fetch_smart`→Mongo вже було зроблено 08-23 (`SyncEngine`), з `kanji/` брати нічого; 16 тестів.
- ✅ `_old_data.zip` (mochi, дампи 2024-03-30…04-21) імпортовано локально командою `wklabs import-raw` (крок 3 [T10](.t/T10-P--full-data-plan.md)): рівно 7 656 нових версій, `history` = 204 479, `events` = 109 285; подій за 2024 стало 26 028. Zip лишається в mochi як джерело, більше з ним нічого робити не треба.
- ⬜ «Повні дані»: решта плану [T10](.t/T10-P--full-data-plan.md) (rsync хвоста зі старого сервера → доімпорт → перевірки), питання [T09](.t/T09-Q--old-server-data.md); чому доповнюємо, а не з нуля — [T11](.t/T11-C--clean-slate-vs-append.md). Перевірено: subjects main/light байт-у-байт однакові, різниця лише в тому, хто зловив версію — обʼєднання в глобальній `history` і є чиста база.
- ⬜ Перенести `history` на vv3 (`mongodump`/`mongorestore`, ~93 MB на диску) + `rebuild-events` там — [deploy/README.md](../deploy/README.md) §8; після деплою бота.
- ⬜ Web + Vue (статистика).

## Наступний крок

- Ти: відповіді `>` у T01/T02 (якщо є правки), токен бота + chat_id форуму → `.env` → локально `uv run wklabs-bot` з реальним Telegram → потім деплой за runbook.
- Далі за деплоєм — історія на сервер (§8 runbook); локальна Mongo `kanji` більше не потрібна (дроп — на твій розсуд).
- Ти: команди з [T12](.t/T12-R--old-server-answers.md) на vv1 (crontab, дата останнього файлу) і rsync у `~/Giga/data/wanikani-server`; вивід — у чат. Я: порівняння дерев → доімпорт → звірка.
