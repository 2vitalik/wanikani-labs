# STATUS LOG — wanikani-labs (новіше вгорі)

`2026-09-10` 🤖 Claude
🟩 Зробили — T08: імпорт історії з файлів у локальну Mongo (173k версій, 101k подій, звірено до одиниці); importer.py + тест
🟨 Далі — бот з реальним Telegram (S), деплой на vv3 (M), потім history на сервер за runbook §8 (S)
🟥 Чекає тебе — BOT_TOKEN / TG_FORUM_CHAT_ID / TG_ADMIN_IDS у .env; `>` у T07/T08; дроп локальної Mongo `kanji` — на твій розсуд

`2026-09-10` 🤖 Claude
🟩 Зробили — T07: бачення бота (фічі, режими, пропозиція черговості кроків)
🟨 Далі — бот з реальним Telegram (S), деплой на vv3 (M); потім крок 2 з T07: сесії + денний підсумок + стрік (M)
🟥 Чекає тебе — `>` у T07 (правки, пріоритети); BOT_TOKEN / TG_FORUM_CHAT_ID / TG_ADMIN_IDS у .env

`2026-09-10` 🤖 Claude
`2026-09-10` · Claude
🟩 Зробили — packages/ (T03); конвенція комітів погоджена (T04→T06) і зафіксована глобально (# git у Shared CLAUDE.md) та в проєкті; 4 коміти за новим форматом
🟨 Далі — бот з реальним Telegram (S), деплой на vv3 за deploy/README.md (M), імпорт історії Giga + rebuild-events (M)
🟥 Чекає тебе — BOT_TOKEN / TG_FORUM_CHAT_ID / TG_ADMIN_IDS у .env; `>` у T06, якщо дефолт «несуміжні тікети через кому» не той

`2026-09-10` 🤖 Claude
`2026-09-10` · Claude
🟩 Зробили — підпроєкти переїхали в packages/ (T03), запропоновано конвенцію комітів (T04/T05); 3 коміти за новим форматом, тести/лінт зелені
🟨 Далі — після твоїх `>` у T05: зафіксувати конвенцію (README/CLAUDE.md, за потреби переписати коміти) (S); далі — бот з реальним Telegram і деплой (M)
🟥 Чекає тебе — `>` у T05 (Q1–Q8); BOT_TOKEN / TG_FORUM_CHAT_ID / TG_ADMIN_IDS у .env

`2026-08-23` 🤖 Claude
🟩 Зробили — v1: монорепо lib/cli/bot/web, sync engine (baseline+інкремент), events, бот у dry-run, 14 тестів, deploy-шаблони; дизайн T01, рішення T02
🟨 Далі — тест бота з реальним Telegram (S), деплой на vv3 за deploy/README.md (M), імпорт історії Giga + rebuild-events (M)
🟥 Чекає тебе — BOT_TOKEN / TG_FORUM_CHAT_ID / TG_ADMIN_IDS у .env; `>`-правки в T01/T02, якщо є
