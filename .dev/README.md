# wanikani-labs — робоча памʼять проєкту

Мета: збирати **все**, що дає WaniKani API, у MongoDB — поточний стан, повну історію версій і похідні події (ревʼю, SRS-переходи, рівні, зміни контенту) — і жити з цим далі: Telegram-бот із дайджестами у форум-топіки (зараз), веб зі статистикою (фаза 3). Продовження старого cron-скрапера (`mochi/`, файли 2022–2026) і проміжної спроби `kanji/`.

Метод — жива спека: `/Users/v4u/Dropbox/v4/Dev/My/dev-md-rules/APPROACH.md` (компактний шар DEV.md — у кожній сесії). Реєстр тікетів — [MAP.md](MAP.md), дерево вузлів — [TREE.md](TREE.md), журнал — [CHANGELOG.md](CHANGELOG.md), голос проєкту — [STATUS.md](STATUS.md).

## Конвенції

- Репо = uv-workspace монорепо, namespace `wklabs`: `lib/` (ядро) · `cli/` (`wklabs`) · `bot/` (`wklabs-bot`) · `web/` (`wklabs-web`, порт 8100) · `vue/` (фаза 3, порт 5100) · `deploy/` (юніт, env-шаблон, runbook) — дизайн і чому саме так: [T01](.t/T01-P--architecture-v1.md), стартові рішення: [T02](.t/T02-R--decisions-2026-08-23.md).
- Код/ідентифікатори/коментарі — EN; документація й спілкування — UA; коміти робить лише Vitalik.
- Стек: Python ≥3.12, PyMongo native async (не motor), httpx, pydantic-settings, aiogram 3, APScheduler 3, typer, FastAPI; ruff + pyright + pytest (тести — на реальній локальній Mongo, БД `wanikani_labs_test`).
- Секрети — `.env` (git-ignored) локально, `shared/env` на сервері; акаунти WK — `WK_TOKEN__<KEY>`.
- Проєкт №10 у реєстрі портів DEV.md.

## Вузли

Поки всі тікети в корені `.t/`; вузли зʼявляться, коли наросте (кандидати: `lib/` схема й sync, `bot/` сповіщення, `web/`).

## Стан

- ✅ v1 зібрано й перевірено локально: baseline-sync обох акаунтів (23 840 обʼєктів, 18 с, 52 запити), інкрементальний — 3 с; бот у dry-run поллить; 14 тестів, ruff/pyright чисті.
- ⬜ Деплой на vv3 — [deploy/README.md](../deploy/README.md); потрібні від тебе `BOT_TOKEN`, `TG_FORUM_CHAT_ID`, `TG_ADMIN_IDS`.
- ⬜ Імпорт історії з `~/Giga/data/wanikani` + `rebuild-events` (фаза 3 плану T01).
- ⬜ Web + Vue (статистика).

## Наступний крок

- Ти: відповіді `>` у T01/T02 (якщо є правки), токен бота + chat_id форуму → `.env` → локально `uv run wklabs-bot` з реальним Telegram → потім деплой за runbook.
