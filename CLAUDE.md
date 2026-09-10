# wanikani-labs — конвенції для агента

- Памʼять проєкту — `.dev/` (README → тікети → MAP/TREE); правила методу — DEV.md/APPROACH.md (глобально).
- Код/ідентифікатори/коментарі/докстрінги — EN; документація й чат — UA; коміти робить лише користувач; повідомлення — за глобальною конвенцією (`# git` у глобальному CLAUDE.md: `<type>[(scope)]: <summary>, tNN`), «чому» — [T04](.dev/.t/T04-P--commit-convention.md).
- Монорепо uv-workspace, namespace `wklabs.*`; підпроєкти — `packages/<name>/` (`lib`, `cli`, `bot`, `web`); нові модулі — в потрібний підпроєкт, не в корінь.
- Сирі обʼєкти WaniKani зберігати незмінними (`item`); похідне (`events`) має перебудовуватись з `history` — не писати логіку, яку не можна відтворити з історії.
- Перед завершенням: `uv run pytest` (локальна Mongo), `uv run ruff check . && uv run ruff format --check .`, `uv run pyright`.
- Секрети лише в `.env`/`shared/env`; не виводити токени в чат/лог.
