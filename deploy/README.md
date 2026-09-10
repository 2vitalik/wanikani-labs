# Деплой на vv3 — wanikani-labs-bot

Слідує `vps-infra/steps/80_site.md` (§1 юзер, §2 дерево, §4 uv runtime, §5 юніт) і юніту бота з `vps-infra/.dev/.t/T20--nure-bot/log/`. Рядки ≤70 символів — для копіпасту.

Словник: slug `wanikani-labs` · юзер `app-wanikani-labs` · дерево `/srv/wanikani-labs/` · БД `wanikani_labs` · юніт `wanikani-labs-bot.service` (пізніше `wanikani-labs-web.service`, порт 8100).

## 1. Юзер і дерево

```sh
S=wanikani-labs
sudo adduser --system --group --home /srv/$S \
  --no-create-home --shell /usr/sbin/nologin app-$S
sudo install -d -m 750 -o root -g app-$S /srv/$S
sudo install -d -m 750 -o root -g app-$S /srv/$S/repo
sudo install -d -m 750 -o root -g app-$S /srv/$S/shared
sudo install -m 640 -o root -g app-$S /dev/null /srv/$S/shared/env
```

## 2. Mongo: юзер бази

Як у T20 (`mongosh --file` з root-only `.js`, потім `shred -u`): користувач `wanikani_labs`, роль `readWrite` лише на `wanikani_labs`, пароль 30 алфанумеричних символів (без екранування в URI). База в шляху URI = робоча = authSource.

## 3. env

`deploy/env.example` → `/srv/wanikani-labs/shared/env` (заповнити токени; `TG_ADMIN_IDS` — через кому).

## 4. Код і venv

Deploy key read-only у `shared/.ssh/`, `git init -b main` + `remote add` + `fetch` + `reset --hard` (не `clone`, щоб права на `repo/` лишились). Далі:

```sh
R=/srv/wanikani-labs/repo; V=/srv/wanikani-labs/venv
sudo UV_PROJECT_ENVIRONMENT=$V uv sync --frozen --no-dev --project $R
ls $V/bin | grep wklabs      # wklabs, wklabs-bot, wklabs-web
```

Python: системний 3.12 достатньо (`requires-python >= 3.12`) — крок з `/opt/uv/python` не потрібен.

## 5. Юніт

```sh
sudo cp $R/deploy/wanikani-labs-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wanikani-labs-bot
journalctl -u wanikani-labs-bot -f
sudo etckeeper commit "systemd: add wanikani-labs-bot.service"
```

Очікуване в журналі: `MongoDB connected` → `forum topics ready` → `scheduler started` → `polling as @…` → через ~2 с `sync incremental done … (baseline)` → через ~20 с акаунти.

## 6. Перевірка

- У форумі зʼявились 6 топіків; `/status` у будь-якому топіку від адміна відповідає.
- Після перших ревʼю в WaniKani — дайджест у `📝 <acc> · reviews` протягом 5 хв.

## 7. Редеплой

```sh
sudo git -C $R fetch origin main && sudo git -C $R reset --hard origin/main
sudo UV_PROJECT_ENVIRONMENT=$V uv sync --frozen --no-dev --project $R
sudo systemctl restart wanikani-labs-bot
```

Якщо змінювався `uv.lock` — спершу `uv lock` локально і push, інакше `--frozen` відмовить.

## 8. Історія (разово)

Імпорт з `~/Giga/data/wanikani` зроблено локально 2026-09-10 (T08): `history` = 196 823 док., ~455 MB даних / ~93 MB на диску (WiredTiger), індекси ~72 MB. Далі — `mongodump --db wanikani_labs --collection history` → `mongorestore` на vv3 (через ssh-тунель), далі `wklabs rebuild-events -y` на сервері. Або rsync файлів (1.6 GB) і `wklabs import-files` там — диск 17 GB вільних, але перший варіант ощадніший.
