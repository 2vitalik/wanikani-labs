# T29 · Чати як ціль доставки v1: реєстр, picker, /chats, /setup з пресетами — звіт

`2026-09-12` · ⚙️ задача · готово (код, фаза 1), живий прогін у Telegram — твій крок

Дизайн — [T22](../T22-P--chats-delivery-model.md) / [T23](../T23-P--bot-ux-chats.md) з правками [T26](../T26-C--chats-presets-and-rights.md); рішення — [T27](../T27-R--chats-decisions.md), [T28](../T28-Q--chats-questions-2.md) за рекомендаціями; план і повторний прохід по небезпечних місцях — [plan.md](plan.md).

## Зроблено

**lib**
- `chats.py` (новий; чати винесено з `delivery.py`): `Chat` (тип, `is_forum`, `status` member/administrator/restricted/left/kicked/unknown, `rights` {can_post, can_manage_topics, can_delete, can_pin}, `member_can_topics`, `member_ids` + `members.<id>.{via, seen_at}`, `topics.<thread>.{name, by_bot, bot_name, closed, seen_at}`, `preset`, `added_by`, `checked_at`, `last_seen_at`, `migrated_to`, `greeted_at`, `forgotten_at`), `Rights`, `Topic`, `Inspection`; `ChatRepo`: `seen` (дешевий upsert з будь-якого апдейту), `apply_inspection`, `set_status`, `add_member`, `remember_topic` / `topic_closed` / `topic_gone`, `set_preset`, `set_greeted`, `forget`, `migrate` (group → supergroup), `ensure_private`, `visible_to` (приват + чати, де користувач відомий; адмін — усі), `normalize_legacy` (T18-поля `set_up_by`/`layout`/`bot_is_admin` → нова форма, раз на старті); чиста `hints(chat)` — коди підказок за таблицею T22 §5.
- `delivery.py`: лише маршрути. `Route` + `status`/`error`/`error_at`, `subscribers`, `settings`, `updated_by`; `RouteRepo` + `set_thread(by=)` (нова ціль = здорова), `rename_thread`, `clear_thread`, `set_error` (True лише коли помилка нова → власнику один раз), `clear_error`, `disable_for_owner`, `migrate_chat`. Пресети: `PRESETS = per_category · per_account · one_topic · general`, `preset_topic_name` (`📝 Vitalik · reviews` · `Vitalik` · `WaniKani` · General). `LAYOUT_*` і `layout` прибрано.
- `db.py`: індекси `tg_chats.member_ids`, `tg_chats.status`, `tg_routes.status`.

**bot**
- `chat_inspect.py`: `inspect_chat` (`get_chat` + `get_chat_member(me)` → `Inspection`; `None` = бота там нема), `verify_member` (жива перевірка членства, коли бот адмін).
- `middleware.py`: `ChatMiddleware` — перший outer на message/callback/my_chat_member: реєструє чат, автора як учасника, гілку з повідомлення (`forum_topic_created` / `reply_to_message.forum_topic_created`); кеш у памʼяті, `last_seen_at` не частіше ніж раз на 10 хв. Приватний чат теж реєструється — його документ = «людина писала боту в приваті» (умова, чи можна DM). `UserMiddleware` тепер і на `my_chat_member`.
- `handlers/membership.py`: `my_chat_member` (додали → інспекція + учасник + привітання: DM тому, хто додав, якщо є приватний чат, інакше один рядок у чат, раз; викинули → маршрути off, статус, DM власникам; у приваті заблокували бота → приватні маршрути off), `migrate_to/from_chat_id` (чат і маршрути переїжджають), `forum_topic_edited/closed/reopened`.
- `handlers/chats.py`: `/chats` (список: приват, чати з ✓ кількістю своїх маршрутів, `⚠️ removed me`), картка (права, підказки, «що сюди йде» з власниками, `topics known`, `last preset`), `📬 Deliver here…` → пресети (форум з правами — чотири; інакше одна кнопка «General»), `🧵 Topics` (список відомих), `📨 Send test` (помилка → переінспекція + чесний alert), `🔄 Refresh`, `🚫 Stop here` (лише свої маршрути, акаунт без доставки повертається в приват), `🗑 Forget` (лише для зниклих), `🧹 Close` у групі, `Later`; `➕ Add a chat` → reply-клавіатура `request_chat` (`📂 Group or forum` з правами admin + Manage Topics · `👥 Chat I'm already in` · `📢 Channel` · Cancel) → `chat_shared` → інспекція → картка; deep-link `/start chat_<id>`; `✨ Recreate topic` для маршруту з «topic deleted». Усі `ch:`-кнопки працюють і в групі: чат — з callback data, видимість перевіряється на кожне натискання, пресет рухає лише акаунти того, хто натиснув.
- `handlers/setup.py`: легкий `/setup` — інспекція, реєстрація, рядок прав + підказки, ряд пресетів (або одна кнопка), `⚙️ Configure here` (картка в чаті), `⚙️ In private` (deep-link). Редактор з галочками прибрано.
- `topics.py`: `ensure_thread` нічого не створює (маршрут без гілки = General); `create`, `rename`, `apply_preset` (move акаунтів + гілки за назвою: знайти або створити; без прав — General), `recreate` (за `thread_title`, разом із сусідами, що втратили ту саму гілку), `rename_account(old, new)` — лише гілки `by_bot`, чию назву ніхто не міняв.
- `notifier.py`: `send_one` → (id, код помилки): `Forbidden` → маршрути чату off + `kicked` + DM власникам; `thread not found` → `thread_id` скинуто, гілка з реєстру геть, `status: error "topic deleted"`, DM з `✨ Recreate`; `TOPIC_CLOSED` → `closed` у реєстрі + error + DM; «not enough rights» → error + DM. DM лише коли помилка нова; успіх скидає `error`.
- `keyboards.py` / `texts.py`: нові екрани, таблиця однорядкових підказок (`HINTS`), `ROUTE_ERRORS`, секція «Chats & forums» у `/help`; `SetupState`/`kb_setup` прибрано. `callbacks.py`: `ChatCb("ch")`, `RouteCb.recreate`, `NavCb chats/addchat`; `SetupCb`/FSM `Setup` прибрано.
- `accounts.py`: `📬 Delivery` → `Move all to` застосовує памʼять `preset` чату (або per_category/General); `➕ Add a chat`; `_user_chat` → `visible_chat`.
- `__main__.py`: `/chats` у приватних командах, `normalize_legacy` на старті, обидва middleware на message/callback/my_chat_member (`my_chat_member` потрапляє в `allowed_updates` автоматично — перевірено `resolve_used_update_types`).

## Перевірено

- `uv run pytest` — 53 тести (lib 34: + `test_chats.py` — seen/inspection/members/topics/visible_to/forget/migrate/normalize_legacy, `hints()` таблиця; `test_delivery.py` — пресети, здоровʼя маршруту; bot 19: пресети й доставка, `rename_account` за правилом T26 §3, topic deleted → General + DM + Recreate, TOPIC_CLOSED, kicked; хендлери — додали руками (DM / рядок у чат), picker + видимість (жива перевірка членства), легкий `/setup` і спільна картка в групі, міграція, події гілок, `thread_of`; UI — картка, підказки, клавіатури, picker, ліміт 64 байти callback data). `ruff check` + `format --check` чисто; `pyright` 0 помилок.
- Диспетчер збирається з новими роутерами; dry-run старт локально (див. лог сесії).

## Хвости

- Живий Telegram не проганявся: перевірити наживо (1) `➕ Add a chat` → чи Telegram справді додає бота з правами в обраний форум, (2) `chat_shared` містить `title` (Bot API 7.0+), (3) `/setup` у форумі → пресет → 4 гілки → дайджест у гілку, (4) `⚙️ Configure here` у групі, (5) видалити гілку руками → DM з `✨ Recreate`.
- Фаза 2 (окрема задача): ціль на кожному маршруті (`tgt:` — чат → гілка зі списку / General / нова), `🧵 ➕ New topic` / `✏️ Rename` з UI, налаштування `silent` / `items` з реєстру, `subscribers` для `subjects` (зараз — один перемикач на чат, як у T18), `can_edit` для адмінів чату (зараз чужі маршрути в картці лише видно).
- `ChatMiddleware` реєструє чат на будь-який апдейт, включно з `my_chat_member` «kicked» (без шкоди: статус ставить хендлер після).
- Локальна база: `normalize_legacy` виконається на першому старті бота (у dry-run теж).
