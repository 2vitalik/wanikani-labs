# T21 · Readback: рішення по акаунтах (T17, T20, чат 2026-09-12)

`2026-09-12` · ✔️ readback

Контекст:
- джерела: чат 2026-09-12 (13 пунктів → [T19](T19-C--accounts-answers.md)) і «T20: все за рекомендаціями, стартуй T18»; дизайн — [T14](T14-P--accounts-model.md) / [T15](T15-P--bot-ux-accounts.md) з правками T19; задача — [T18](T18--accounts-v1/plan.md).

## Рішення (усі — «за рекомендацією»)

- **Доступ:** `ACCESS_POLICY=open` (дефолт) — новий користувач одразу `active`, адмінам повідомлення `🆕 joined` з кнопкою `🚫 Block`; `approve` і `closed` лишаються значеннями env.
- **Токени:** Fernet, ключ `WKLABS_SECRET_KEY` в env (1Password + `shared/env`); `wklabs gen-key`; без ключа бот не стартує.
- **Ключі акаунтів:** завжди `wk_id[:8]` (колізія → 12); `main` → `07fff792`, `light` → `27f9b9f5` мігруються командою `wklabs accounts migrate-keys` (локально — я, на vv3 — ти, з зупиненим ботом).
- **Env:** `WK_TOKEN__*` і `TG_FORUM_CHAT_ID` прибрано; акаунти — лише бот / CLI, форум — лише `/setup`. Лишаються `BOT_TOKEN`, `TG_ADMIN_IDS`, `MONGO_*`, `WKLABS_SECRET_KEY`, `ACCESS_POLICY`, інтервали.
- **FSM:** `PyMongoStorage` (колекція `tg_fsm`) + детектор UUID-токена в приваті незалежно від стану.
- **Колекції:** `accounts` (WK) · `tg_users · tg_chats · tg_routes · tg_messages · tg_fsm`; `tg_topics` нема — назва топіка живе в маршруті; при `🗑 Remove` маршрути вимикаються, не видаляються.
- **Ролі:** `admin` — лише з `TG_ADMIN_IDS` (ти); решта `user`; кнопки «Make admin» у v1 нема.
- **Purge** — лише CLI, лише `status: removed`. **Дефолт доставки** — приват. **Топіки при remove** — лишати. **Чужий дубль `wk_id`** — відмова + сигнал адмінам. **Тексти** — EN.

## Твої думки та питання

> 
