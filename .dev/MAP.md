# MAP — реєстр тікетів

<!-- автоген: `dev map` (або `dev gen`), руками не редагувати -->

Наступний вільний ID: **T31** · тікетів: 30 · дерево вузлів — [TREE.md](TREE.md)

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
| — | [T14](.t/T14-P--accounts-model.md) | 💡 | accounts-model | Акаунти в Mongo: модель, схема, міграція, безпека токенів, код | 🟢 ⬜ |
| — | [T15](.t/T15-P--bot-ux-accounts.md) | 💡 | bot-ux-accounts | UX бота для акаунтів: команди, меню, діалоги, екрани | 🟢 ⬜ |
| — | [T16](.t/T16-B--accounts-alternatives.md) | 🧠 | accounts-alternatives | Варіанти ключових рішень: ключ акаунта, токени, доставка, доступ | 🟢 ⬜ |
| — | [T17](.t/T17-Q--accounts-questions.md) | ❓ | accounts-questions | Питання до дизайну акаунтів (критичні позначено) | 🔴 ⬜ |
| — | [T18](.t/T18--accounts-v1/plan.md) | ⚙️ | accounts-v1 | Акаунти v1: users/accounts/chats/routes + UI бота — план | 🟢 ⬜ |
| — | [T19](.t/T19-C--accounts-answers.md) | 🔆 | accounts-answers | Відповіді на питання з чату по дизайну акаунтів і що переглянуто | 🟢 ⬜ |
| — | [T20](.t/T20-Q--accounts-questions-2.md) | ❓ | accounts-questions-2 | Питання раунду 2: доступ, Fernet, міграція ключів, env | 🔴 ⬜ |
| — | [T21](.t/T21-R--accounts-decisions.md) | ✔️ | accounts-decisions | Readback: рішення по акаунтах (T17, T20, чат 2026-09-12) | 🟢 ⬜ |
| — | [T22](.t/T22-P--chats-delivery-model.md) | 💡 | chats-delivery-model | Чати як ціль доставки: реєстр чатів, топіки, маршрути, налаштування, код | 🟢 ⬜ |
| — | [T23](.t/T23-P--bot-ux-chats.md) | 💡 | bot-ux-chats | UX бота для чатів і форумів: команди, екрани, вибір цілі, топіки, довідка | 🟢 ⬜ |
| — | [T24](.t/T24-B--chats-alternatives.md) | 🧠 | chats-alternatives | Варіанти рішень по чатах: дискавері, вибір чату, реєстр топіків, /setup, налаштування | 🟢 ⬜ |
| — | [T25](.t/T25-Q--chats-questions.md) | ❓ | chats-questions | Питання до дизайну чатів і доставки (критичні позначено) | 🔴 ⬜ |
| — | [T26](.t/T26-C--chats-presets-and-rights.md) | 🔆 | chats-presets-and-rights | Пресети замість розкладок, /setup з «налаштувати тут», права на зміни маршрутів | 🟢 ⬜ |
| — | [T27](.t/T27-R--chats-decisions.md) | ✔️ | chats-decisions | Readback: рішення по чатах з чату 2026-09-12 (T25 + пресети + /setup + права) | 🟢 ⬜ |
| — | [T28](.t/T28-Q--chats-questions-2.md) | ❓ | chats-questions-2 | Питання раунду 2 по чатах: пресет за замовчуванням, права, видалена гілка, меню в чаті | 🟢 ⬜ |
| — | [T29](.t/T29--chats-v1/plan.md) | ⚙️ | chats-v1 | Чати як ціль доставки v1: реєстр, picker, /chats, /setup з пресетами — план | 🟢 ⬜ |
| — | [T30](.t/T30--chats-v2/plan.md) | ⚙️ | chats-v2 | Чати v2: ціль на маршруті, гілки з UI, налаштування, підписники, права адмінів чату — план | 🟢 ⬜ |
