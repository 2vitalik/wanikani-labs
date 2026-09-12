# T29 · Чати як ціль доставки v1: реєстр, picker, /chats, /setup з пресетами — план

`2026-09-12` · ⚙️ задача

Контекст:
- дизайн — [T22](../T22-P--chats-delivery-model.md) / [T23](../T23-P--bot-ux-chats.md) з правками [T26](../T26-C--chats-presets-and-rights.md); рішення — [T27](../T27-R--chats-decisions.md); [T28](../T28-Q--chats-questions-2.md) — за рекомендаціями (права: власник · адмін бота · адмін чату в межах чату; видалену гілку не перестворювати мовчки; чотири пресети в `/setup`; `WaniKani`; лише `🧹 Close`);
- це фаза 1 з двох: реєстр чатів і три шляхи знайомства, `/chats` з карткою, пресети, легкий `/setup` з `⚙️ Configure here`, здоровʼя маршрутів. Фаза 2 (окрема задача): ціль на кожному маршруті (`tgt:`), створення/перейменування гілок з UI, налаштування `silent`/`items`, `subscribers` для `subjects`, `can_edit` для адмінів чату.

## Повторний прохід по небезпечних і незручних місцях (нове, поверх T24 §10)

1. `my_chat_member` не проходить через `UserMiddleware`, якщо не зареєструвати middleware і для цього типу апдейту → хендлер без `user` впаде. Реєструємо `dp.my_chat_member.outer_middleware(...)`.
2. Заблокований користувач у групі: `UserMiddleware` мовчки обриває апдейт → чат не зареєструється. `ChatMiddleware` — окремий і **перший** outer, реєструє чат незалежно від статусу людини.
3. Запис у Mongo на кожне повідомлення групи (бот-адмін бачить усе): кеш у памʼяті «останній знімок чату» — пишемо лише коли щось нове; `last_seen_at` — не частіше ніж раз на 10 хв.
4. Міграція group → supergroup приходить двома сервісними повідомленнями (`migrate_to_chat_id` у старому, `migrate_from_chat_id` у новому) — обробляємо обидва ідемпотентно; маршрути й документ чату переїжджають один раз.
5. `chat_shared` може прийти для чату, куди бота не додали (користувач скасував діалог або не має права додавати) → `get_chat` падає → чесне повідомлення «I'm not in that chat», не виняток у лог.
6. Reply-клавіатура picker-а лишається на екрані, якщо людина замість вибору надішле команду: `one_time_keyboard=True` + `ReplyKeyboardRemove` на `chat_shared`/Cancel.
7. Старі документи `tg_chats` мають `set_up_by` і `layout`: одноразова нормалізація на старті (`set_up_by` → учасник `via: setup`, `layout: topics` → `preset: per_category`), `from_doc` читає обидві форми.
8. `TopicManager.ensure_thread` більше **не створює** гілок при доставці (гілки — лише пресети/UI): маршрут без `thread_id` = General. Інакше «видалену гілку не перестворювати» не виконати.
9. Помилка доставки в гілку: `message thread not found` → `thread_id` скидається, `status: error "topic deleted"`, одне DM власнику з `✨ Recreate`; `TOPIC_CLOSED` → `status: error "topic closed"`, DM з підказкою; `Forbidden` → маршрути чату off + `status: kicked` + DM власникам. DM — лише коли статус *змінився* (не на кожен полл).
10. Успішне надсилання скидає `error` лише якщо він був (нуль зайвих записів).
11. Callback у групі тисне будь-хто: кожен `ch:`-хендлер перевіряє видимість чату (учасник / адмін бота) і **пресети рухають лише акаунти того, хто натиснув**.
12. `📨 Send test` — найдешевша діагностика прав: помилка показується як підказка, а не ковтається.
13. Deep-link `/start chat_<id>` містить `-` у від'ємному id — дозволено в `start`-параметрі (`A-Za-z0-9_-`).
14. `get_chat_member(me)` для звичайного члена не містить прав → `can_post` беремо з `ChatFullInfo.permissions.can_send_messages`; канал → `can_post_messages` адміна.
15. `leave_chat` породжує ще один `my_chat_member` (`left`) — хендлер ідемпотентний.
16. `accounts → Delivery → Move all to <chat>` після зникнення `layout`: переїзд + застосування памʼяті `preset` чату (є) або General.
17. `edit_forum_topic` дозволений і без `can_manage_topics` для гілок, які створив сам бот (Bot API) — `rename_account` це використовує, але лише для гілок `by_bot`, чию назву ніхто не міняв.

## Кроки

**1. lib**
- [ ] `chats.py` (новий, з `delivery.py`): `Rights`, `Topic`, `Inspection`, `Chat` (status/rights/members/topics/preset/added_by/migrated_to/greeted_at/forgotten_at), `ChatRepo` (`seen`, `apply_inspection`, `set_status`, `add_member`, `remember_topic`, `topic_closed`, `topic_gone`, `set_preset`, `set_greeted`, `forget`, `migrate`, `ensure_private`, `visible_to`, `normalize_legacy`), `hints()`; тести
- [ ] `delivery.py`: `Route` + `status/error/subscribers/settings/updated_by`; `RouteRepo` + `clear_thread`, `set_error`, `clear_error`, `migrate_chat`, `for_chat_full`; `PRESETS`, `preset_topic_name`; `LAYOUT_*` геть; тести
- [ ] `db.py`: індекси `tg_chats.member_ids`, `tg_chats.status`

**2. bot — знайомство**
- [ ] `chat_inspect.py`: `inspect_chat`, `verify_member` (API → `Inspection`)
- [ ] `middleware.py`: `ChatMiddleware` (кеш, учасники, гілки з повідомлень); `UserMiddleware` і для `my_chat_member`
- [ ] `handlers/membership.py`: `my_chat_member` (реєстр, привітання DM/рядок, kicked → off), `chat_shared`, `migrate_*`, `new_chat_title`, `forum_topic_*`
- [ ] `topics.py`: `create`, `rename`, `apply_preset`, `recreate`, `rename_account` за правилом 17; `ensure_thread` без створення

**3. bot — UI**
- [ ] `callbacks.py`: `ChatCb("ch")`, `RouteCb.action += recreate`, `NavCb` += `chats/addchat`, FSM `PickChat`
- [ ] `keyboards.py` / `texts.py`: `/chats`, картка чату (приват і група), пресети, picker (reply), stop-confirm, topics list, greeting, підказки (таблиця T23 §5)
- [ ] `handlers/chats.py`: `/chats`, картка, `➕ Add a chat`, пресети, `📨 Send test`, `🔄 Refresh`, `🚫 Stop here`, `Forget`, `🧵 Topics` (список), `🧹 Close`, deep-link
- [ ] `handlers/setup.py`: легкий `/setup` (пресети або `📬 Deliver here`, `⚙️ Configure here`, `⚙️ In private`)
- [ ] `handlers/accounts.py`: delivery-екран без `layout`; `Move all to` → пресет чату
- [ ] `notifier.py`: здоровʼя маршрутів (п. 9–10), DM власникам; `__main__.py`: `/chats`, middleware, `normalize_legacy`

**4. Перевірка й доки**
- [ ] `uv run pytest` · ruff · pyright; тести хендлерів membership/chats з побудованими апдейтами і FakeBot
- [ ] `.dev/README.md` (конвенції: `/chats`, `/setup`), CHANGELOG, `report.md`; runbook — лише якщо змінюється env (не має)

Поза фазою 1: `tgt:` вибір цілі на маршруті, `🧵 ➕/✏️`, налаштування маршруту, `subscribers`, `can_edit` для адмінів чату, делегування.
