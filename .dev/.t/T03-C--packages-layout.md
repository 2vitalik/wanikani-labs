# T03 · Розкладка packages/: підпроєкти lib/cli/bot/web під одним дахом

`2026-09-10` · 🔆 clarification

Контекст:
- твоя пропозиція з чату 2026-09-10: зібрати підпроєкти в `packages/`, як робилось в іншому проєкті;
- ⚠️ переглядає дерево репо з [T01](T01-P--architecture-v1.md) (§ «Структура репо»); T01 лишається як був.

## Чому погоджуюсь

- Корінь стає читабельним: конфіги, README, `.dev/`, `deploy/` — і одна тека з кодом; одразу видно, що є пакетом, а що обвʼязкою.
- Конфіги стають глобами замість переліків: `members = ["packages/*"]`, ruff `src = ["packages/*/src"]`, pytest `testpaths = ["packages"]`, pyright `include = ["packages"]` — новий підпроєкт не вимагає правити чотири файли.
- Не плутаються імена: `lib/`, `bot/`, `web/` у корені виглядають як звичайні теки, а не як самостійні дистрибутиви `wklabs-*`.
- Ціна нульова: namespace `wklabs.*`, entrypoints (`wklabs`, `wklabs-bot`, `wklabs-web`) і деплой (`uv sync --project $R`) не залежать від шляху до пакета.

## Що змінилось

- `git mv lib cli bot web packages/` — історія файлів збережена як rename.
- `pyproject.toml` (workspace members, ruff src, pytest testpaths) і `pyrightconfig.json` — на глоби `packages/…`.
- `uv.lock` перелоковано (editable-шляхи `packages/<name>`), `uv sync` перевстановив пакети.
- Нові шляхи в `README.md`, `.env.example`, `.gitignore` (`packages/vue/dist/`), `.dev/README.md`, `CLAUDE.md`.
- `deploy/`, `scripts/`, `.dev/` лишаються в корені — це не пакети.
- PyCharm `.idea/wklabs-*.iml` (git-ignored): content roots переписані на `packages/…`.

Перевірено: `uv run pytest` — 14 passed; `ruff check` / `ruff format --check` / `pyright` — чисто.

## Домовленість на майбутнє

- Усе, що є окремим дистрибутивом або фронтом, — `packages/<name>/`; `vue/` у фазі 3 — `packages/vue/` (порт 5100).
- Тека в `packages/` без `pyproject.toml` (той самий `vue/`) — uv її пропускає, глоб лишається; перевірено на порожній теці.

## Твої думки та питання

> 
