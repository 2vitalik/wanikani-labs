# T23 · UX бота для чатів і форумів: команди, екрани, вибір цілі, топіки, довідка

`2026-09-12` · 💡 proposal

Контекст:
- модель і правила — [T22](T22-P--chats-delivery-model.md); нинішній UX акаунтів — [T15](T15-P--bot-ux-accounts.md) (картка, `📬 Delivery`, `/setup` з галочками); принципи ті самі: мало команд, один живий екран на чат (кнопки редагують те саме повідомлення), діалог лише там, де треба ввести текст, EN;
- твої вимоги з чату: вибір чату зі списку, гілку — зі списку або створити/перейменувати тут же; `/setup` лишити як альтернативу для тих, кому командами зручніше, але легшим; права не ховати; підказати, що форум можливий; лаконічно, зрозуміло з першого разу; маленькі підказки на місці, довідка окремо, якщо треба;
- варіанти — [T24](T24-B--chats-alternatives.md); питання — [T25](T25-Q--chats-questions.md).

## 1. Команди

Приват: `/accounts` · **`/chats`** (нове: чати, куди я можу доставляти) · `/status` · `/help`. Адмін: + `/admin`, `/sync`, `/sync_full`.
Група/форум/канал: `/setup` (легкий, §4) · `/status` · `/ping`. Приватні команди в групі → «continue in private» + кнопка (є).
Deep-link `/start chat_<id>` — з `/setup` і з привітання одразу відкриває картку чату.

Два входи до одного й того ж: **від чату** (`/chats` → картка → що сюди йде) і **від акаунта** (`/accounts` → картка → `📬 Delivery` → категорія → куди). Обидва ведуть у той самий екран маршруту (§3.4).

## 2. `/chats`

**Список**
```
💬 Chats I can post to
[🔒 private · here]
[🗂 WK forum · forum · 2 topics]
[👥 Study group · group]
[⚠️ Old forum · removed me]
[➕ Add a chat]
Don't see a chat? Add it with ➕, or send /setup there.
```
Порядок: приват, потім за `last_seen_at`. Адмін бачить усі чати; чужі — з позначкою `· N users`.

**Картка чату**
```
🗂 WK forum · forum
me: admin ✅ · topics ✅ · delete ✅
Delivering here:
📝 Vitalik · reviews → 📝 Vitalik · reviews
🏆 Vitalik · milestones → 🏆 Vitalik · milestones
📚 subjects → 📚 subjects · you + 1
layout for new routes: topic per account & category

[📬 Deliver here…]  [🧵 Topics]  [📨 Send test]
[⚙️ Layout]  [🔄 Refresh]  [🚫 Stop here]
[« Chats]
```
- Рядок `me:` — знімок прав (§5 тексти); є проблема → замість ✅ рядок-підказка, напр. `me: member · topics ✗ — make me admin with Manage Topics, then 🔄 Refresh`.
- `📬 Deliver here…` → вибір акаунта (якщо їх >1) → застосувати `layout` чату до всіх категорій акаунта (те саме, що «Move all to» у T15) → назад у картку з результатом одним рядком.
- `🧵 Topics` — лише форум (§2.1). `⚙️ Layout` — лише форум із правами: три радіо-варіанти (§2.2). `📨 Send test` — одне тестове повідомлення в General/чат.
- `🚫 Stop here` — вимкнути всі **свої** маршрути в цей чат (не чужі), двокроково; бот з чату не виходить. Для `left/kicked` замість цього `Forget`. `Leave chat` — лише адмінам чату/бота, у тому ж підтвердженні.
- Приватний чат — картка без `🧵/⚙️/🚫`, лише «що сюди йде» і `📨 Send test`.

**2.1 `🧵 Topics`**
```
🧵 Topics — WK forum · 4 known
📝 Vitalik · reviews · by me
🏆 Vitalik · milestones · by me
💬 Chat
📌 Rules · closed
I only see topics I created or saw messages in.
[➕ New topic]  [✏️ Rename…]  [« Chat]
```
- `➕ New topic` → діалог `Topic name:` (1–128) → `create_forum_topic` → назад у список із `✅ created`. Без прав → кнопки нема, рядок-підказка є.
- `✏️ Rename…` → список гілок, які можна перейменувати (створені ботом; усі — якщо ти адмін чату) → `New name for «📝 Vitalik · reviews»:` → готово, маршрути з цією гілкою оновлюють `thread_title`.

**2.2 `⚙️ Layout`**
```
⚙️ Layout — WK forum · applies to routes you move here
[● topic per account & category]   📝 Vitalik · reviews, 🏆 Vitalik · milestones
[○ one topic per account]          Vitalik
[○ no topics (General)]
[↪️ Apply to my routes here now]  [« Chat]
```

**2.3 `➕ Add a chat`** — єдиний екран не з inline-кнопками (обмеження Telegram: `request_chat` живе лише в reply-клавіатурі):
```
Pick where I should post 👇
If I'm not there yet, Telegram adds me with the rights I need
(admin + Manage Topics for forums).
Prefer commands? Add me to the chat and send /setup there.
[📂 Group or forum]  [📢 Channel]
[✖️ Cancel]
```
- `📂 Group or forum` — `request_chat(chat_is_channel=False, bot_administrator_rights={can_manage_topics}, request_title=True)`; `📢 Channel` — `chat_is_channel=True, bot_administrator_rights={can_post_messages}`. Форуми окремо не фільтруємо: користувач може вибрати звичайну групу — картка підкаже про Topics.
- Після вибору → reply-клавіатура знімається → інспекція → картка чату з рядком `✅ added` зверху. Не вдалося (бота не додали, чат не знайдено) → «I'm not in that chat. If you're its admin, add me there; otherwise ask an admin to.» + `[« Chats]`.

## 3. Від акаунта: `📬 Delivery`

**3.1 Екран доставки акаунта** (замінює T15)
```
📬 Delivery — Vitalik
📝 reviews → WK forum › 📝 Vitalik · reviews 🔕
🏆 milestones → private · here
[📝 reviews]  [🏆 milestones]
[➡️ Move all to…]  [« Back]
```
Кожна категорія — один рядок на ціль (кілька цілей → кілька рядків); ⚠️ перед рядком, якщо `status: error` (§5).

**3.2 Категорія** (список її маршрутів)
```
📝 reviews — Vitalik
[✅ WK forum › 📝 Vitalik · reviews 🔕]
[🚫 private · here]
[➕ Also deliver to…]  [« Delivery]
```
Кнопка маршруту → його екран (3.4). `➕ Also deliver to…` → вибір цілі (3.3) → новий маршрут.

**3.3 Вибір цілі** (два кроки, без FSM — усе в callback data)
```
Where should 📝 reviews of Vitalik go?
[🔒 private · here]
[🗂 WK forum]   ← current
[👥 Study group]
[➕ Add a chat]  [« Back]
```
Форум → крок 2:
```
🗂 WK forum — which topic?
[✨ Auto: 📝 Vitalik · reviews]   ← бот створить/знайде за layout
[💬 General]
[📝 Vitalik · reviews · by me]
[📌 Rules]
[➕ New topic…]  [« Chats]
Auto topics follow the account name; picked ones I never rename or delete.
```
Група/канал/приват → без кроку 2. Вибір → екран маршруту з `✅ moved` / `✅ added`.

**3.4 Екран маршруту**
```
📝 reviews — Vitalik
→ WK forum › 📝 Vitalik · reviews · auto
[✅ on]  [🔕 silent: off]  [📄 items: all]
[📍 Change target]  [📨 Send test]  [🗑 Remove route]
[« 📝 reviews]
silent — no notification sound · items — all / wrong only / counts only
```
- Кнопки налаштувань генеруються з реєстру ([T22](T22-P--chats-delivery-model.md) §3): bool — перемикач, choice — цикл; рядок-підказка внизу — з `help` реєстру. Налаштування, не застосовне до категорії (`items` для milestones), не показується.
- `🗑 Remove route` — вимикає й ховає (документ лишається, як усюди); останній маршрут акаунта прибрати не можна — замість цього пропонується «Move to private».
- Спільний маршрут (`subjects`) показує `· you + 1` і замість `🗑` — `[🔕 Unsubscribe]`.

## 4. `/setup` у чаті — легкий

```
🛠 WK forum · forum · me: admin ✅ · topics ✅
[📬 Deliver my digests here]  [⚙️ Configure in private]
```
- Реєструє чат, інспектує права, показує підказку, якщо чогось бракує (§5). Одне повідомлення, дві кнопки; кнопки працюють лише для того, хто надіслав команду (інші отримують «send /setup yourself»).
- `📬 Deliver my digests here` — усі активні акаунти автора → сюди за `layout` чату (топіки створюються) → редагує повідомлення: `✅ Vitalik, 2vitalik → here · 4 topics created. Fine-tune in private: /chats`. Немає акаунтів → «add one in private first: /accounts» + кнопка.
- `⚙️ Configure in private` — deep-link у картку чату.
- Повний редактор з галочками (T15 §2) прибирається — його заміняє картка чату в приваті. Рішення — [T25](T25-Q--chats-questions.md) Q2.

## 5. Тексти підказок (одним рядком, на місці)

| ситуація | рядок |
|---|---|
| basic group | `💡 Topics need a supergroup: Group settings → Topics converts it (I'll follow the new id).` |
| supergroup, not forum | `💡 Want one topic per account? Group settings → Topics, then 🔄 Refresh.` |
| forum, not admin | `⚠️ Topics need me as admin with Manage Topics → then 🔄 Refresh.` |
| forum, admin, no Manage Topics | `⚠️ Missing right: Manage Topics.` |
| can't post | `⚠️ I can't post here (restricted). Ask an admin to allow me.` |
| channel, no post right | `⚠️ Need the Post Messages right.` |
| left / kicked | `🚫 I'm no longer in this chat. Add me back or Forget it.` |
| route error: topic closed | `⚠️ topic closed — reopen it or 📍 change target` |
| route error: topic gone (manual) | `⚠️ topic deleted — delivering to General; 📍 pick another` |
| route error: no rights | `⚠️ can't post there — check my rights (🔄 Refresh in /chats)` |
| picked chat, bot absent | `I'm not in that chat. If you're its admin, add me; otherwise ask an admin.` |

Принцип: спочатку що не так, потім одна дія, що це лагодить. Без абзаців.

## 6. Довідка

`/help` отримує секцію (коротко):
```
Chats & forums
/chats — where I post. ➕ picks a chat from your list; Telegram adds me
with the rights I need. Forum = one topic per account (or per category,
or one stream) — your choice per chat. I only know topics I created or
saw messages in; ➕ New topic and General always work.
Rights I need: post messages; forums — admin + Manage Topics.
```
Плюс кнопка `ℹ️` на екрані вибору гілки й у `🧵 Topics` → той самий абзац у тому ж повідомленні з `« Back`. Окремих сторінок довідки більше не треба: усе інше — рядки-підказки на місці.

## 7. Повідомлення від бота (не у відповідь)

- Додали руками, автор відомий: приват `👋 I'm in «WK forum» now · forum ✅ · topics ✅` + `[📬 Deliver here…] [Later]`. Автор невідомий, писати можна: у чат один рядок `Hi! WaniKani digests here → /setup, or open me in private → /chats.`
- Викинули: власникам маршрутів `🚫 Removed from «WK forum» — reviews, milestones of Vitalik paused. /chats to pick another.`
- Помилка маршруту: один раз до успіху (§5).
- Дайджести — як зараз; `silent` → без звуку.

## 8. Callback data і стани

`ch:<chat_id>:<action>[:<arg>]` (card · deliver · topics · layout · layout_set · apply_layout · refresh · test · stop · stop_yes · forget · leave · newtopic · rename · rename_pick) · `tgt:<key>:<cat>:<chat>[:<thread|auto|general>]` · `tp:<chat>:<thread>:<action>` · `rt:<id>:<on | set:<key> | target | test | remove | unsub>` · `nav:chats | addchat`. Найдовший — 53 байти. FSM: `TopicName {chat, thread}` (створити/перейменувати), `PickChat` (лише щоб прибрати reply-клавіатуру після `chat_shared`/Cancel).

## Твої думки та питання

> 
