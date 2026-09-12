# T30 · Чати v2: ціль на маршруті, гілки з UI, налаштування, підписники, права адмінів чату — звіт

`2026-09-13` · ⚙️ задача · готово (код), живий прогін фаз 1–2 у Telegram — твій крок

План — [plan.md](plan.md); дизайн — [T22](../T22-P--chats-delivery-model.md) §2–4, [T23](../T23-P--bot-ux-chats.md) §2.1/§3, [T26](../T26-C--chats-presets-and-rights.md) §5; фаза 1 — [T29](../T29--chats-v1/report.md).

## Зроблено

**lib**
- `route_settings.py` (новий): реєстр `Setting(key, kind bool|choice, default, label, help, choices, categories)`; `SILENT` (усі категорії) і `ITEMS` (лише reviews: all · wrong only · counts only); `for_category`, `effective(route, account_settings)` (дефолти ← шар акаунта ← шар маршруту, невалідні значення ігноруються), `next_value` (перемикач / цикл), `display`, `help_line`. Нова настройка = один рядок реєстру + її використання.
- `delivery.py`: `subscribe / unsubscribe(category, chat, tg_id)` — спільний маршрут глобальної категорії живий, поки є підписники; `add_target` («також доставляти сюди»), `move_route` (та сама група → інша гілка на місці; інший чат → старий off, новий on), `set_setting`.

**bot**
- `digest.py`: `render(..., items=)` — reviews: `wrong` лишає лише ❌ і ⬇️ без списків уроків/розблокувань, `none` — лише заголовок з лічильниками.
- `notifier.py`: рендер на маршрут за `effective()` (кеш за `items`), `disable_notification` з `silent`.
- `handlers/common.py`: `Perm` + `can_edit` — власник акаунта й адмін бота: усе; адмін чату (`get_chat_member`, кеш 60 с у `AppContext.admin_cache`): on/off, гілка в межах свого чату, налаштування; учасник чату на спільному маршруті: своя підписка + налаштування; решта — лише перегляд. `route_screen` — екран маршруту з кнопками за правами.
- `handlers/delivery.py` (новий, працює і в групі): `📬 Delivery` акаунта (категорії кнопками, `📚 subjects` по чатах як підписка «я + N», `➡️ Move all to…`) → категорія (цілі, `➕ Also deliver to…`) → маршрут (`✅ on/🚫 off`, `🔕 Silent`, `📄 Items`, `📍 Change target`, `📨 Send test`, `✨ Recreate topic`) → вибір чату (видимі, куди можу писати; адмін чату — лише свій) → вибір гілки (`✨ Auto` за памʼяттю пресету чату, `💬 General`, відомі відкриті, `➕ New topic…`). Контекст вибору — у FSM `PickTarget` (переживає рестарт), callback несе лише `(chat, thread)`; застарілий екран → «open Delivery again».
- `handlers/chats.py`: `🧵 Topics → ➕ New topic / ✏️ Rename…` (діалог `TopicName`; перейменовувати — гілки бота або всі, якщо ти адмін чату; створена з picker-а гілка одразу стає ціллю), `🧭 Routes here` (усі маршрути в чат → екран маршруту за `can_edit`), `📚 Subjects: on/off` і `🛠 System: on/off` (адміни бота) у картці чату як особиста підписка.
- `keyboards.py` / `texts.py`: нові екрани; `accounts.py` — delivery-частина переїхала в `delivery.py`.

## Перевірено

- `uv run pytest` — 60 тестів (+7: реєстр налаштувань і шари, subscribe/move/add, `items` у рендері, `silent` + `items` у доставці, `can_edit` (власник / адмін бота / учасник / адмін чату / спільний маршрут) і екран маршруту, вибір цілі (`_resolve_thread` auto/id/General, move/add, екрани), гілка з UI (create / rename / погана назва), підписки через картку чату (дві людини → один маршрут, нікого → off; system лише адмінам)); `ruff check` + `format --check` чисто; `pyright` 0 помилок. Диспетчер збирається (7 роутерів, `my_chat_member` у `allowed_updates`), найдовші callback data ≤ 43 байти.

## Хвости (живий прогін у Telegram — обидві фази)

1. `➕ Add a chat` → чи Telegram справді додає бота з правами в обраний форум; чи `chat_shared` несе назву.
2. `/setup` у форумі → пресет → 4 гілки → дайджест у гілку; `⚙️ Configure here` → картка в групі → `🧹 Close`.
3. Видалити гілку руками → DM з `✨ Recreate` → натиснути.
4. `📬 Delivery → 📝 reviews → маршрут → 📍 Change target → форум → ➕ New topic…` → назва → маршрут показує нову гілку; потім `🔕 Silent: on` → наступний дайджест без звуку; `📄 Items: wrong only`.
5. `🧵 Topics → ✏️ Rename…` для гілки бота; спроба перейменувати людську гілку без адмінства чату — має не пропонуватись.
6. Другий акаунт (`2vitalik`): `📚 Subjects` у спільному чаті з обох — один маршрут, підписники 2; відписати одного — маршрут живий.
7. Адмін чату (інший користувач) з групи: `🧭 Routes here` → чужий маршрут → `📍 Change target` пропонує лише цей чат.

Поза v2: делегування «мої маршрути тут можуть міняти всі» (місце — гілка в `can_edit` + кнопка), шар налаштувань акаунта (часовий пояс), `subjects.scope`, режими session/daily (T07 крок 2).
