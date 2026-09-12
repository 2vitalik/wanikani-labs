# T22 · Чати як ціль доставки: реєстр чатів, топіки, маршрути, налаштування, код

`2026-09-12` · 💡 proposal

Контекст:
- твій запит у чаті 2026-09-12: керувати доставкою з приватного меню — бот знає всі чати, куди його додали, показує їх списком, ціль (чат → гілка форуму) обирається з цього списку; гілки створювати/перейменовувати з приватного UI; `/setup` у чаті — можливо лишити для тих, кому зручніше командами; чати ідентифікувати завжди (додали до привʼязки, додав хтось невідомий); кілька користувачів/акаунтів в одному чаті — без конфліктів, спільне (`subjects`) не дублювати; невеликий механізм налаштувань доставки з заділом на більше; права на гілки не ховати, а показувати, чого бракує; підказати, що форум узагалі можливий; лаконічно, але зрозуміло з першого разу;
- база — [T14](T14-P--accounts-model.md) §1–2 (`tg_chats · tg_routes`), правки [T19](T19-C--accounts-answers.md) §6 (без `tg_topics`), рішення [T21](T21-R--accounts-decisions.md), реалізація [T18](T18--accounts-v1/report.md); бачення — [T07](T07-P--bot-vision.md) §4 (три шари налаштувань: дефолти → акаунт → призначення);
- перевірено в aiogram 3.30 (Bot API): `KeyboardButtonRequestChat` (`chat_is_forum`, `bot_is_member`, `bot_administrator_rights`, `user_administrator_rights`, `request_title`) → повідомлення `chat_shared`; апдейт `my_chat_member` (`ChatMemberUpdated`: `from_user`, `old/new_chat_member` з правами); `create/edit/close/reopen/delete_forum_topic`, `*_general_forum_topic`, `get_forum_topic_icon_stickers`; сервісні повідомлення `forum_topic_created/edited/closed/reopened`, `general_forum_topic_hidden/unhidden`, `new_chat_title`, `migrate_to_chat_id/migrate_from_chat_id`; `ChatFullInfo.is_forum/permissions`, `ChatMemberAdministrator.can_manage_topics/can_delete_messages/can_pin_messages/can_post_messages`, `ChatMemberRestricted.can_send_messages`. **Списку топіків форуму в Bot API нема** — бот знає лише ті, що створив сам або побачив у повідомленнях;
- UX (екрани, тексти) — [T23](T23-P--bot-ux-chats.md); варіанти з аргументами — [T24](T24-B--chats-alternatives.md); питання — [T25](T25-Q--chats-questions.md).

## 0. Суть одним абзацом

Три способи «познайомити» бота з чатом сходяться в один реєстр `tg_chats`: **нативний вибір чату** з приватного меню (кнопка `request_chat` — Telegram показує список чатів користувача, фільтрує форуми, сам додає бота з потрібними правами), **`/setup` у чаті** (для тих, кому зручніше командами) і **пасивне спостереження** (апдейт `my_chat_member`, коли бота додали руками; будь-яке повідомлення в чаті). Далі все керується з приватного меню: акаунт → категорія → чат → гілка; гілки створюються/перейменовуються звідти ж; реєстр памʼятає права бота й чесно показує, чого бракує. Маршрут отримує шар налаштувань (перші два — `silent` і `items`), спільні категорії в одному чаті — список підписників замість дубля.

## 1. Реєстр чатів `tg_chats` — джерела й життєвий цикл

Усі джерела ідемпотентні (upsert), кожен доповнює те, що знає:

| джерело | коли | що дає |
|---|---|---|
| `chat_shared` (picker) | користувач вибрав чат у приваті | `chat_id`, `title`; Telegram сам додав бота з правами (якщо його там не було й користувач має право додавати) |
| `my_chat_member` | бота додали / підвищили / обмежили / викинули; бот вийшов | `status` (member · administrator · restricted · left · kicked), права, `from_user` = хто зробив → `added_by`, учасник |
| `/setup`, `/ping`, будь-яка команда в чаті | явно | title, `is_forum`, учасник = автор; `/setup` — ще й повна інспекція прав |
| будь-який апдейт із групи (middleware) | завжди | title, `is_forum`, `last_seen_at`, автор → учасник; `message_thread_id` + `reply_to_message.forum_topic_created` → назва гілки; сервісні `forum_topic_*`, `new_chat_title`, `migrate_*` |
| помилки доставки | Notifier | `Forbidden` → `kicked`; `TOPIC_CLOSED` / thread gone → статус маршруту |

- **Інспекція** `inspect(chat_id)` = `get_chat` + `get_chat_member(me)` → `type`, `title`, `is_forum`, `status`, `rights {can_post, can_manage_topics, can_delete, can_pin}`, `member_can_topics` (чи можуть звичайні учасники створювати топіки — `permissions.can_manage_topics`), `checked_at`. Викликається на `my_chat_member`, `chat_shared`, `/setup`, кнопці `🔄 Refresh`, перед операцією з топіками і після помилки доставки. Не на кожне повідомлення (два API-виклики).
- **Чого реєстр не може:** дізнатись про чати, куди бота додали, поки він не працював понад 24 год (Telegram тримає чергу апдейтів добу), і перелічити чати на старті (методу нема). Тому в UI завжди є рядок «Не бачиш свій чат? Додай через ➕ або надішли там /setup».
- **Міграція group → supergroup** (`migrate_to_chat_id`): id чату змінюється — саме це стається, коли в звичайній групі вмикають Topics. `ChatRepo.migrate(old, new)`: документ переїжджає під новий `_id` (старий лишається зі `migrated_to`), `tg_routes.chat_id` перезаписується. Без цього порада «увімкни Topics» ламала б усі маршрути.
- **Статуси:** `member` · `administrator` · `restricted` · `left` · `kicked` · `unknown` (бачили лише повідомлення, не інспектували). `left/kicked` → маршрути в цей чат вимикаються (з памʼяттю, як `suspended`), картка показує «🚫 мене видалили», кнопка `Forget`.
- **Учасники** `members: [{id, seen_at, via}]` (`via` = added · picked · message · setup · verified) — хто з відомих боту людей точно є в чаті. Це і є «чиї чати показувати кому» (§4).
- **Реєстр гілок** — вбудований у документ чату: `topics: {"<thread_id>": {name, icon_color, by_bot, created_at, seen_at, closed}}` + `general_hidden`. ⚠️ Часткова ревізія [T19](T19-C--accounts-answers.md) §6: там «реєстр топіків зайвий, бо `thread_id` живе в маршруті» — це лишається правдою для доставки, але для **вибору гілки зі списку** потрібні й гілки, не привʼязані до маршрутів (створені людьми). Окремої колекції не треба — мапа в чаті.
- `layout` чату → дефолтна політика гілок для нових/переміщених маршрутів: `topics` (топік на акаунт × категорію — як зараз), `account_topics` (один топік на акаунт, обидві категорії в ньому — новий варіант), `single` (General / без гілок). Змінюється в картці чату; на наявні маршрути діє лише кнопкою «apply to all».
- `greeted_at` — щоб привітання при додаванні (§6) було раз.

## 2. Маршрути `tg_routes` — що додається

```
tg_routes (як у T14 §2) +
  thread_auto   true  — гілку створив бот за layout: перестворює, якщо зникла; перейменовує при зміні label
                false — гілку вибрала людина: бот її не чіпає; зникла → status error + fallback у General
  status        "ok" | "error"      error: "topic closed" | "topic gone" | "no rights" | "forbidden"; error_at
  subscribers   [tg_id]             лише глобальні категорії (subjects, system): enabled = непорожній список
  settings      {silent: bool, items: "all"|"wrong"|"none", …}   шар «призначення» (T07 §4)
  updated_by, updated_at
```

- Ціль маршруту = `(chat_id, thread_id | null)`; `thread_id = null` = приват, група без гілок або General у форумі.
- **Декілька цілей на одну категорію** — модель уже дозволяє (unique = `account × category × chat`): reviews у приват і у форум одночасно. UI дає «➕ also deliver to…».
- **Спільні категорії в спільному чаті:** один маршрут `(null, subjects, chat)` на чат зі списком `subscribers`. Увімкнути = додати себе, вимкнути = прибрати себе; маршрут живий, поки хтось підписаний. Нуль дублювання за побудовою і нуль «я вимкнув — у сусіда зникло». Налаштування маршруту спільні (останній, хто змінив, — у `updated_by`, UI пише «set by …»). Якщо колись зʼявиться фільтр «лише мої предмети» (T07 §2), такий маршрут стає per-account — це вже різний зміст, тому дублювання буде правильним. Per-account категорії двох різних акаунтів в одному чаті — різний зміст, ідуть обидва.
- **Здоровʼя маршруту:** Notifier при помилці надсилання ставить `status: error` з причиною (замість тихого лога), один раз пише власнику в приват («⚠️ reviews → WK forum: topic closed — reopen it or pick another in /chats»), далі мовчить до успіху або зміни цілі. Успішне надсилання скидає в `ok`. У картках — ⚠️ з підказкою.

## 3. Налаштування доставки — механізм

- Реєстр у `lib` (чистий), не окремі поля:
  ```
  Setting(key, kind: bool | choice, default, label, help, choices=(), categories=())
  ROUTE_SETTINGS = (
    Setting("silent", bool, False, "🔕 Silent", "no notification sound"),
    Setting("items", choice, "all", "📄 Items", "which items to list", choices=(("all","all"),("wrong","wrong only"),("none","counts only")), categories=("reviews",)),
  )
  ```
- `effective(route, account) -> dict`: дефолти ← `accounts.settings` ← `routes.settings` (шар акаунта — той самий реєстр із `scope`, зʼявиться з першою настройкою рівня акаунта; кандидат — часовий пояс акаунта, зараз глобальний `settings.tz`).
- UI генерується з реєстру: bool → кнопка-перемикач `🔕 Silent: off`, choice → кнопка-цикл `📄 Items: all → wrong only → counts only`; підказка — рядок `help` під списком. Нова настройка = один рядок у реєстрі + використання у рендері/відправці.
- Перші дві: `silent` → `send_message(disable_notification=True)`; `items` → `render_reviews` фільтрує рядки (`wrong` = лише ❌ і ⬇️; `none` = лише заголовок з лічильниками). Далі кандидати (не зараз): `subjects.scope all|mine` (T07 §2), `pin_level_up` (потрібно `can_pin`), quiet hours, режим `daily` (крок 2 T07).

## 4. Хто що бачить і може (безпека)

- Callback data підробна → кожна дія над чатом перевіряє, що чат **видимий** користувачу: свій приват завжди; група — якщо він у `members`; адмін бота — усе. Чат не в `members` → живий `get_chat_member(chat, user)`, якщо бот адмін там (інакше метод не гарантований) → `via: verified`; не вдалося → «I can't confirm you're in that chat — send /setup there». Це закриває «направити свій спам у чужий чат за id».
- Направляти доставку в чат може будь-який його відомий учасник (не лише адмін чату): він і так може там писати; присутність бота контролюють адміни чату (можуть викинути). Рекомендую саме так — [T25](T25-Q--chats-questions.md) Q3.
- Гілки: **створити** — будь-який видимий учасник (потрібні права бота); **перейменувати** — лише гілки, створені ботом, або якщо користувач адмін чату (перевірка `get_chat_member`). Так бот не стане інструментом перейменування чужих гілок у великому комʼюніті-форумі.
- **Вийти з чату** (`leave_chat`) — адмін чату або адмін бота. **Forget** (прибрати з реєстру, вимкнути маршрути) — будь-який учасник для своїх маршрутів; документ не видаляється (`forgotten_at`), бо бот усе ще в чаті й наступне повідомлення його поверне.
- `system` — лише адміни бота, як було.

## 5. Права та підказки — правила, а не тексти

Чиста функція `hints(chat) -> list[Hint]` над знімком інспекції; тексти — [T23](T23-P--bot-ux-chats.md) §5. Правила:

| стан | що показати |
|---|---|
| приват | нічого, ціль завжди доступна |
| basic `group` | 💡 гілки лише у супергрупах: Group settings → Topics (Telegram сам конвертує; id зміниться — ми обробляємо) |
| `supergroup`, не форум | 💡 Topics вимкнено — увімкни в налаштуваннях групи, буде топік на акаунт/категорію |
| форум, бот не адмін | ⚠️ гілки недоступні: зроби мене адміном з Manage Topics → 🔄 Refresh |
| форум, адмін без `can_manage_topics` | ⚠️ бракує права Manage Topics |
| `restricted` без `can_send_messages` / група забороняє писати | ⚠️ мені заборонено писати тут |
| `left` / `kicked` | 🚫 мене тут нема — додай знову або Forget |
| `channel` без `can_post_messages` | ⚠️ потрібне право Post Messages |
| немає `can_delete_messages` | (лише в довідці: токени в групі не зможу видаляти) |

## 6. Знайомство при додаванні руками

- `my_chat_member` → `member`/`administrator`: інспекція, реєстр, `added_by`. Далі — DM тому, хто додав, якщо він уже писав боту (інакше бот не може почати діалог): «👋 I'm in «WK forum» now · forum ✅ · topics ✅ → [📬 Deliver here…] [Later]». Не можемо DM і можемо писати в чат → один рядок у чат: «Hi! WaniKani digests here: /setup — or open me in private → /chats». Раз на чат (`greeted_at`). Рекомендую — [T25](T25-Q--chats-questions.md) Q10.
- `kicked`/`left` → маршрути off (з памʼяттю), власникам маршрутів — одне повідомлення.
- Права змінилися (`administrator` ↔ `member`, `can_manage_topics`) → оновити знімок; якщо гілки стали недоступні, а маршрути з `thread_id` є — не ламати: доставка піде в наявні гілки (писати в існуючий топік право не потрібне), лише створення нових заблоковано.

## 7. Топіки: що робить бот

- `ensure_thread(route)`: `thread_id` є → він; `thread_auto=false` → як є (null = General); `auto` → за `layout` чату: `topics` → `📝 Vitalik · reviews`, `account_topics` → `Vitalik` (одна гілка на обидві категорії — обидва маршрути отримують той самий `thread_id`), `single` → null. Створене → у `chats.topics` з `by_bot: true`.
- Створити з UI: назва 1–128, колір із 6 дозволених (за категорією або перший вільний); перейменувати: `edit_forum_topic`; результат — у реєстр і в `thread_title` маршрутів, що туди дивляться.
- Навчання з чату: `forum_topic_created` (нова гілка, її `message_thread_id` = id повідомлення), `forum_topic_edited` (нова назва), `closed/reopened`, звичайні повідомлення в гілці (`is_topic_message` + `reply_to_message.forum_topic_created.name`). З privacy mode бот бачить звичайні повідомлення лише як адмін — саме тоді гілки й потрібні, тож збігається.
- `📨 Send test` — на маршруті/чаті: надсилає «✅ test · wanikani-labs» у ціль; найпростіший спосіб перевірити права й гілку до першого дайджесту.
- Гілку, зроблену людиною, бот **не закриває і не видаляє** (Q5).

## 8. Код

`lib` (чисте):
- `chats.py` (виносимо з `delivery.py`): `Chat` (+ `status`, `rights`, `member_can_topics`, `members`, `topics`, `layout`, `added_by`, `migrated_to`, `greeted_at`, `forgotten_at`, `checked_at`), `Topic`, `Rights`, `ChatRepo`: `seen(chat_id, type, title, is_forum, member=…)` (дешевий upsert з middleware) · `apply_inspection(chat_id, info)` · `set_status` · `add_member` · `is_member(chat, tg_id)` · `remember_topic / topic_closed / topic_gone` · `set_layout` · `migrate(old, new)` · `forget` · `visible_to(tg_id, admin)` · `for_user` (заміна нинішнього `set_up_by`-запиту). Чиста `hints(chat)` (§5) і `topics_possible / can_post` як властивості.
- `delivery.py`: `Route` (+ `thread_auto`, `status`, `error`, `subscribers`, `settings`, `updated_by`), `RouteRepo`: `set_target(route, chat_id, thread_id, *, auto, title)` · `add_route(account, category, chat, thread, …)` · `subscribe / unsubscribe(None, category, chat, tg_id)` · `set_setting(route, key, value)` · `set_error / clear_error` · `migrate_chat(old, new)` · `disable_chat` (є) · `layout_title(layout, category, label)` замість `topic_title`; `LAYOUTS = (topics, account_topics, single)`.
- `route_settings.py`: `Setting`, `ROUTE_SETTINGS`, `effective(route, account)`, `next_value(setting, current)` (для кнопки-циклу), валідація.
- `db.py`: індекси `tg_chats.members.id`, `tg_chats.status`; `tg_routes.subscribers`.

`bot`:
- `chat_inspect.py`: `inspect_chat(bot, chat_id) -> Inspection` (get_chat + get_chat_member(me), обробка «chat not found / bot is not a member»), `verify_member(bot, chat_id, user_id)`.
- `middleware.py`: `ChatMiddleware` — на будь-який апдейт із групи/каналу `chats.seen(...)` + учасник + гілка з повідомлення; в памʼяті кеш «останній знімок за chat_id», щоб не писати в Mongo на кожне повідомлення без змін.
- `handlers/membership.py`: `router.my_chat_member` (§6), `chat_shared` (picker → інспекція → картка), сервісні: `migrate_to_chat_id`, `new_chat_title`, `forum_topic_*`, `general_forum_topic_*`.
- `handlers/chats.py`: `/chats`, картка чату, `➕ Add a chat` (reply-клавіатура з `request_chat`, знімається після вибору/Cancel), `🧵 Topics` (список, new/rename — FSM на назву), `🔄 Refresh`, `⚙️ Layout`, `📨 Send test`, `🚫 Stop delivering here`, `Forget`, `Leave` (адмін чату / бота).
- `handlers/delivery.py` (виносимо delivery-екрани з `accounts.py`): `📬 Delivery` акаунта → категорія → вибір чату → вибір гілки (General · відомі · ➕ New topic · ✨ Auto) → екран маршруту (on/off, налаштування з реєстру, ➕ also to…, 📍 change target, 📨 test).
- `handlers/setup.py`: легка версія (Q2): інспекція + картка з двома кнопками `📬 Deliver my digests here` (усі акаунти автора за `layout` чату) і `⚙️ Configure in private` (deep-link `/start chat_<id>` → одразу картка чату).
- `topics.py`: `ensure_thread` за §7, `create(chat, name, color)`, `rename(chat, thread, name)`, `learn(...)`.
- `notifier.py`: `disable_notification` з `effective(...).silent`; `items` → у `render`; помилки → `routes.set_error` + одне DM власнику; успіх → `clear_error`; `thread_auto=false` і гілка зникла → fallback General + error.
- `callbacks.py`: `ChatCb("ch": chat_id, action, arg)`, `TargetCb("tgt": key, cat, chat, thread)` — найдовший `tgt:07fff792:milestones:-1001234567890:123456` = 49 байт ≤ 64 (12-символьний ключ колізії — 53), `TopicCb("tp": chat, thread, action)`, `RouteCb` (+ `on`, `set:<key>`, `test`, `target`); FSM `TopicName {chat, thread|""}`, `PickChat {key, cat}` (лише щоб зняти reply-клавіатуру після `chat_shared`).
- `__main__.py`: `/chats` у приватних командах; `dp.my_chat_member` з `UserMiddleware` (у `ChatMemberUpdated` є `from_user`); `allowed_updates` aiogram виводить з хендлерів — `my_chat_member` потрапить сам.

Тести: `ChatRepo` (seen/inspection/members/topics/migrate/visible_to) · `RouteRepo` (set_target, subscribers, settings effective, migrate_chat, error/clear) · `hints()` таблиця §5 · `route_settings` (next_value, effective з шарами) · Notifier: silent, `items`, manual-thread gone → General + error, success clears · membership-хендлери з побудованими `ChatMemberUpdated`/`Message` (без Telegram) · клавіатури/тексти чисті (розмір callback data ≤ 64 — тест на найдовший).

## 9. Порядок реалізації (дві фази, кожна лишає бота робочим)

1. **Реєстр і знайомство:** `chats.py`, `ChatMiddleware`, `membership.py` (my_chat_member, migrate, service messages), `chat_inspect.py`, `/chats` + картка + `➕ Add a chat` (picker) + `🔄 Refresh` + `📨 Send test`, легкий `/setup`, привітання; Notifier ставить статус маршруту. (~M)
2. **Ціль і налаштування:** `delivery.py` хендлер (категорія → чат → гілка), `topics.py` (create/rename з UI, `account_topics`), `route_settings.py` + екран маршруту, `subscribers` для `subjects`, `items` у рендері. (~M)

Після рішень у [T25](T25-Q--chats-questions.md) — задача-тека з планом.

## 10. Межі й ризики

- `request_chat` — кнопка **reply**-клавіатури (не inline): один екран «вибери чат 👇» виглядає інакше за решту меню; клавіатура знімається одразу після вибору/Cancel. Поведінку «Telegram сам додає бота з правами, якщо його ще нема в чаті» перевірити наживо на першому прогоні (у клієнтах реалізовано, але не в усіх однаково).
- Немає способу перелічити гілки форуму — список у боті = «створені ботом + побачені». У довідці це сказано одним рядком; `➕ New topic` і `General` завжди є.
- Ліміт Telegram ~20 повідомлень/хв у групу: багато акаунтів в одному чаті → `TelegramRetryAfter` уже обробляється затримкою.
- Група → супергрупа після «увімкни Topics»: маршрути переїжджають автоматично (§1), але `tg_messages` зі старим `chat_id` лишаються історією — не важливо.
- Два бот-процеси з одним `BOT_TOKEN` (локально + vv3) — `TelegramConflictError`, як і раніше (runbook §6).

## Твої думки та питання

> 
