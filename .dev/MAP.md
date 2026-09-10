# MAP — реєстр тікетів

<!-- автоген: `dev map` (або `dev gen`), руками не редагувати -->

Наступний вільний ID: **T14** · тікетів: 13 · дерево вузлів — [TREE.md](TREE.md)

Типи: `Q`❓ питання · `P`💡 пропозиція · `C`🔆 clarification · `B`🧠 brainstorm · `R`✔️ readback · `S`📝 summary · `D`🗄️ digest (на пенсії) · ⚙️ задача (тека, без літери). state: 🟢/🔴 — чи чекає твоєї відповіді · 🟩/⬜ — чи інтегровано в README вузла.

| Вузол | ID | Т | Файл | Про що | state |
|-------|----|---|------|--------|:-----:|
| — | [T01](.t/T01-P--architecture-v1.md) | 💡 | architecture-v1 | Архітектура v1: монорепо, Mongo-схема, бот-поллер, план запуску | 🟢 ⬜ |
| — | [T02](.t/T02-R--decisions-2026-08-23.md) | ✔️ | decisions-2026-08-23 | Readback: стартові рішення (структура, Telegram, топіки, процес) | 🟢 ⬜ |
| — | [T03](.t/T03-C--packages-layout.md) | 🔆 | packages-layout | Розкладка packages/: підпроєкти lib/cli/bot/web під одним дахом | 🟢 ⬜ |
| — | [T04](.t/T04-P--commit-convention.md) | 💡 | commit-convention | Конвенція комітів: Conventional Commits + суфікс тікетів | 🟢 ⬜ |
| — | [T05](.t/T05-Q--commit-convention.md) | ❓ | commit-convention | Питання до конвенції комітів | 🔴 ⬜ |
| — | [T06](.t/T06-R--commit-convention-answers.md) | ✔️ | commit-convention-answers | Readback: відповіді на T05 (конвенція комітів) | 🟢 ⬜ |
| — | [T07](.t/T07-P--bot-vision.md) | 💡 | bot-vision | Бачення бота: продукт, фічі, режими (фон дорожньої карти) | 🟢 ⬜ |
| — | [T08](.t/T08-C--import-history.md) | 🔆 | import-history | Імпорт історії з файлів у Mongo: що вже є, прогін локально | 🟢 ⬜ |
| — | [T09](.t/T09-Q--old-server-data.md) | ❓ | old-server-data | Питання: старий сервер, доступ, rsync, вимкнення cron | 🟢 ⬜ |
| — | [T10](.t/T10-P--full-data-plan.md) | 💡 | full-data-plan | План «повні дані»: старий сервер → файли → Mongo, якість і перевірки | 🟢 ⬜ |
| — | [T11](.t/T11-C--clean-slate-vs-append.md) | 🔆 | clean-slate-vs-append | Чистий лист чи доповнення локальної бази перед дампом на сервер | 🟢 ⬜ |
| — | [T12](.t/T12-R--old-server-answers.md) | ✔️ | old-server-answers | Readback: відповіді на T09 (vv1, сам виконуєш, окрема тека, cron ще 1–2 тижні) | 🟢 ⬜ |
| — | [T13](.t/T13-C--server-tail-import.md) | 🔆 | server-tail-import | Хвіст з vv1: порівняння дерев, мапа акаунтів, доімпорт, розклад cron | 🟢 ⬜ |
