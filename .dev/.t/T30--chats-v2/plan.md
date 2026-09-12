# T30 · Чати v2: ціль на маршруті, гілки з UI, налаштування, підписники, права адмінів чату — план

`2026-09-13` · ⚙️ задача

Контекст:
- фаза 2 з [T29](../T29--chats-v1/report.md) («Хвости»); дизайн — [T22](../T22-P--chats-delivery-model.md) §2–4, [T23](../T23-P--bot-ux-chats.md) §2.1, §3, [T26](../T26-C--chats-presets-and-rights.md) §5; рішення — [T27](../T27-R--chats-decisions.md), [T28](../T28-Q--chats-questions-2.md) за рекомендаціями;
- живий прогін фази 1 ще не робився (твій крок після цієї задачі — список у T29 report «Хвости» + нове звідси).

## Уточнення до дизайну (дрібне, з коду)

- Контекст вибору цілі (акаунт · категорія · режим move/add/all · маршрут) — у FSM (`PyMongoStorage`, переживає рестарт), callback несе лише `(chat, thread)`: інакше `tgt:` не влазить у 64 байти з ObjectId. Застарілий екран → «open Delivery again».
- `🗑 Remove route` не робимо: `🚫 off` на маршруті — те саме; вимкнені маршрути не показуються.
- Після зникнення редактора `/setup` адміни бота втратили `🛠 system` — повертається кнопкою в картці чату (лише адмінам бота); `📚 subjects` — там само, як підписка «я».
- `can_edit`: власник акаунта й адмін бота — усе; адмін чату — on/off, гілка в межах свого чату, налаштування; учасник — лише своє. Перевірка адмінства чату — `get_chat_member` з кешем на хвилину в `AppContext`.
- Спільна картка чату отримує `🧭 Routes here` — усі маршрути в цей чат → екран маршруту з кнопками за `can_edit` (так адмін чату щось може з групи).

## Кроки

**1. lib**
- [ ] `route_settings.py`: `Setting` (bool | choice, default, label, help, categories), `ROUTE_SETTINGS = silent · items(reviews)`, `for_category`, `effective(route, account_settings)`, `next_value`, `display`; тести
- [ ] `delivery.py`: `subscribe / unsubscribe` (глобальні категорії: `enabled = subscribers ≠ ∅`), `add_target`, `move_route`, `set_setting`; тести

**2. bot — рендер і доставка**
- [ ] `digest.py`: `render(..., items=)` для reviews (`all · wrong · none`)
- [ ] `notifier.py`: рендер на маршрут за `effective()`, `disable_notification` з `silent`
- [ ] `context.py`: кеш адмінів чату; `handlers/common.py`: `Perm`, `can_edit`, `route_screen`

**3. bot — UI**
- [ ] `callbacks.py`: `TargetCb("tgt": chat, thread)`, `TopicCb("tp": chat, thread, action)`, FSM `PickTarget`, `TopicName`; дії `AccCb cat`, `RouteCb card/toggle/set/target/test`, `ChatCb routes/subj/sys/newtopic/rename`
- [ ] `handlers/delivery.py` (новий, без фільтра «лише приват»): екран доставки акаунта → категорія → маршрут (on/off, налаштування, 📍 Change target, 📨 test) → вибір чату → вибір гілки (✨ Auto · 💬 General · відомі · ➕ New topic) → застосувати; `➕ Also deliver to…`; `➡️ Move all to…` (пресет чату)
- [ ] `handlers/chats.py`: `🧵 Topics → ➕ New topic / ✏️ Rename…` (свої гілки або адмін чату), `📚 Subjects: on/off`, `🛠 System: on/off` (адмін бота), `🧭 Routes here`
- [ ] `keyboards.py` / `texts.py`: нові екрани; `accounts.py` — delivery-частина переїжджає

**4. Перевірка й доки**
- [ ] `uv run pytest` · ruff · pyright; тести: settings/effective/items, silent у send, subscribe, move/add target, can_edit, target flow (функції), rename з UI
- [ ] `report.md`, README (стан, наступний крок з нагадуванням про живий прогін), CHANGELOG, STATUS
