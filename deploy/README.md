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

Юніт читає цей файл двічі: `EnvironmentFile=` (змінні процесу) і `Environment=WKLABS_ENV_FILE=…` (той самий файл для pydantic-settings) — як `NURE_ENV_FILE` у nure-students. `.env` у `repo/` на сервері немає й не треба. CLI на сервері — з тим самим перемикачем:

```sh
sudo WKLABS_ENV_FILE=/srv/wanikani-labs/shared/env \
  /srv/wanikani-labs/venv/bin/wklabs status
```

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

Імпорт з `~/Giga/data/wanikani` зроблено локально 2026-09-10 (T08): `history` = 218 704 док. (файли до 2026-09-10 + `_old_data.zip`; T13), ~0.5 GB даних / ~0.12 GB на диску (WiredTiger). Переносити **лише** `history` — чому: T11. Порядок: відновити **до** першого старту бота, потім `rebuild-events -y`, потім `enable --now`.

Локально:

```sh
mongodump --db wanikani_labs --collection history --gzip \
  --archive=history.gz && scp history.gz vv3:/tmp/
```

На vv3 — пароль не набирати й не світити в історії/`ps`: URI вже лежить у `shared/env`, mongorestore читає його з root-only YAML (`--config`), файл одразу shred:

```sh
sudo sh -c 'umask 077; printf "uri: %s\n" \
  "$(grep ^MONGO_URI= /srv/wanikani-labs/shared/env | cut -d= -f2-)" \
  > /root/restore.yml'
sudo mongorestore --config /root/restore.yml --gzip \
  --archive=/tmp/history.gz --nsInclude wanikani_labs.history
sudo shred -u /root/restore.yml /tmp/history.gz
sudo WKLABS_ENV_FILE=/srv/wanikani-labs/shared/env \
  /srv/wanikani-labs/venv/bin/wklabs rebuild-events -y
```

Запасний варіант без файлу — mongorestore сам спитає пароль, якщо дати `--username` без `--password`:

```sh
mongorestore --host 127.0.0.1 --username wanikani_labs \
  --authenticationDatabase wanikani_labs --gzip \
  --archive=/tmp/history.gz --nsInclude wanikani_labs.history
``` Далі — `mongodump --db wanikani_labs --collection history` → `mongorestore` на vv3 (через ssh-тунель), далі `wklabs rebuild-events -y` на сервері. Або rsync файлів (1.6 GB) і `wklabs import-files` там — диск 17 GB вільних, але перший варіант ощадніший.
