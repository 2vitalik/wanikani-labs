# T04 · Конвенція комітів: Conventional Commits + суфікс тікетів

`2026-09-10` · 💡 proposal

Контекст:
- твоє побажання з чату 2026-09-10: тип-префікси (`feat`, `fix`, `docs`, `chore`…), тікети — в кінці через кому, короткий заголовок за конвенцією, деталі — лаконічним списком у тілі;
- як є: перший коміт — 101 символ у заголовку, без тіла; у `vps-infra` заголовки до 115 символів, суфікс `, t35-38` уже вживається;
- питання для погодження — окремо в [T05](T05-Q--commit-convention.md).

## Формат

```
<type>[(<scope>)]: <summary>, t<NN>[-<NN>…]

- <деталь>
- <деталь>
```

- **Заголовок ≤ 72 символів** разом із суфіксом; ціль — 50–60. На цій межі `git log --oneline` і GitHub не обрізають.
- `type` — з таблиці нижче; `scope` — необовʼязково, імʼя пакета/зони: `lib`, `cli`, `bot`, `web`, `deploy`, `dev`.
- `summary` — EN, наказовий спосіб, з малої літери, без крапки: `move subprojects into packages/`, не `Moved…`/`Moves…`.
- **Суфікс тікетів** — `, tNN`; кілька — через дефіс `t01-02` (перелік, не діапазон); без тікета суфікс пропускається.
- **Тіло** — після порожнього рядка, лише список `- …`: один рядок ≤ 72 символів на пункт, факт без пояснень (пояснення — у тікеті). Для однорядкової зміни тіло не потрібне.
- Трейлери (`Co-Authored-By`, `Claude-Session`) — у кінці після порожнього рядка, коли коміт робить агент.

## Типи

| type | коли |
|---|---|
| `feat` | нова можливість, яку видно користувачу/оператору |
| `fix` | виправлення поведінки |
| `refactor` | зміна коду без зміни поведінки: переїзди, перейменування |
| `test` | лише тести |
| `docs` | README, `.dev/` (тікети, CHANGELOG, STATUS), коментарі |
| `chore` | конфіги, залежності, tooling, деплой-шаблони |
| `perf` · `ci` · `build` · `style` | за потреби, стандартний набір Conventional Commits |

- Код + тікети того ж рішення — один коміт, тип за кодом (`feat`, не `docs`).
- Заголовок тягне на два типи — знак різати коміт.

## Приклади — повідомлення цієї сесії

Перший коміт (переписаний замість `t01-02: bootstrap wanikani-labs monorepo (…)`):

```
feat: bootstrap monorepo with sync engine and bot, t01-02

- uv workspace: lib / cli / bot / web, namespace wklabs
- sync engine: baseline + incremental (updated_after, ETag)
- append-only history, events derived from diffs
- Telegram bot in dry-run: poller, forum topics, digests
- deploy templates: systemd unit, env, runbook
- 14 tests on local Mongo; ruff + pyright clean
```

Переїзд у `packages/` ([T03](T03-C--packages-layout.md)):

```
refactor: move subprojects into packages/, t03

- lib/ cli/ bot/ web/ -> packages/<name>/ (git mv)
- workspace, ruff, pytest, pyright: globs over packages/
- uv.lock relocked; README, .env.example, .gitignore paths
```

Ця конвенція:

```
docs: propose commit convention, t04-05

- T04 proposal, T05 questions
- .dev/README.md, CLAUDE.md: link the convention
```

## Де зафіксувати

- `.dev/README.md` → «Конвенції» — один рядок + лінк сюди; жива форма, правиться зі зміною правила.
- `CLAUDE.md` проєкту — рядок для агента (формат + лінк), бо це інструкція на кожну сесію.
- Глобальний `~/.claude/CLAUDE.md` → `# git` описує старий формат `t<ID>: summary`; якщо конвенція стає спільною для всіх проєктів — правити там (твій файл, сам не чіпаю).

## Твої думки та питання

> 
