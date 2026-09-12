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

`deploy/env.example` → `/srv/wanikani-labs/shared/env`: `BOT_TOKEN` (BotFather), `TG_ADMIN_IDS` (через кому), `WKLABS_SECRET_KEY` (`wklabs gen-key`; копію — в 1Password: без нього токени акаунтів не розшифрувати), `ACCESS_POLICY` (`open` за замовчуванням), Mongo. Токенів WaniKani і форуму в env **немає** (T21): акаунти додаються через бота в приваті (`/accounts → ➕`) або `wklabs accounts add`, форум — командою `/setup` у самому форумі.

Без `BOT_TOKEN` бот працює в dry-run: полить WaniKani, але до Telegram не підключається і на команди не відповідає. Без `WKLABS_SECRET_KEY` бот не стартує (`wklabs gen-key` → у env → restart).

Перевірити, що заповнено (довжини значень, без самих значень):

```sh
sudo awk -F= '/^(BOT_TOKEN|TG_ADMIN_IDS|WKLABS_SECRET_KEY)=/ {print $1, length($2)}' \
  /srv/wanikani-labs/shared/env
```

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

Очікуване в журналі (`sudo journalctl -u wanikani-labs-bot -n 50 --no-pager` — без `sudo` системні юніти не видно): `MongoDB connected` → `forum topics ready` → `scheduler started` → `polling as @…` → через ~2 с `sync incremental done … (baseline)` → через ~20 с акаунти. Якщо замість `polling as` є `dry-run` — порожній `BOT_TOKEN` (§3).

## 6. Перевірка

- `/ping` у приваті чи в будь-якому чаті відповідає **будь-кому**: аптайм, час останнього sync, твій Telegram id (+ `chat id`/`thread` у групі). Якщо після `/ping` нема слова `admin` — цей id треба дописати в `TG_ADMIN_IDS` → `restart`.
- `/start` у приваті → `➕ Add account` → вставити токен WaniKani (бот видаляє повідомлення, відповідає «synced: …»). `/accounts` — список і картка акаунта.
- Форум: додати бота адміном з правом Manage Topics → `/setup` у форумі → галочки акаунтів, `topics per account`, `📚 subjects`, `🛠 system` → Apply: топіки створюються одразу. Після перших ревʼю в WaniKani — дайджест у `📝 <label> · reviews` протягом 5 хв.
- Хто стукав, а бот проігнорував: `journalctl -u wanikani-labs-bot | grep 'ignored update'`. Бот не відповідає нікому — шукати `TelegramConflictError` (той самий токен поллить ще один процес, напр. локальний `uv run wklabs-bot`).

## 7. Редеплой

```sh
sudo git -C $R fetch origin main && sudo git -C $R reset --hard origin/main
sudo UV_PROJECT_ENVIRONMENT=$V uv sync --frozen --no-dev --project $R
sudo systemctl restart wanikani-labs-bot
```

Якщо змінювався `uv.lock` — спершу `uv lock` локально і push, інакше `--frozen` відмовить.

## 8. Історія (разово)

Імпорт з `~/Giga/data/wanikani` зроблено локально 2026-09-10 (T08): `history` = 218 704 док. (файли до 2026-09-10 + `_old_data.zip`; T13), ~0.5 GB даних / ~0.12 GB на диску (WiredTiger). Переносити **лише** `history` — чому: T11. Порядок: краще відновити **до** першого старту бота, потім `rebuild-events -y`, потім `enable --now`. Якщо бот уже стартував — теж нормально: mongorestore напише `continuing through error: E11000 duplicate key` на кожну версію, яку бот уже зібрав сам (2026-09-11 на vv3: 194 771 відновлено, 23 933 дублікатів — сума = весь локальний `history`); зміст не страждає, далі так само `rebuild-events -y` (він позначає всі події як надіслані — старих дайджестів у Telegram не буде).

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

## 9. Акаунти з env у Mongo (разово, 2026-09)

Після редеплою коду з T18 акаунти живуть у Mongo під ключами `wk_id[:8]`; старі `main`/`light` у даних треба перейменувати **до** старту нового бота (бот зупинений):

```sh
sudo systemctl stop wanikani-labs-bot
W=/srv/wanikani-labs/venv/bin/wklabs
E=WKLABS_ENV_FILE=/srv/wanikani-labs/shared/env
sudo $E $W accounts migrate-keys --dry-run   # main → 07fff792, light → 27f9b9f5
sudo $E $W accounts migrate-keys
sudo $E $W gen-key                            # → WKLABS_SECRET_KEY у shared/env (+ 1Password)
sudo systemctl start wanikani-labs-bot
```

Далі в приваті з ботом: `/accounts → ➕ Add account` → токен `main`, потім `light` — бот упізнає акаунти за `wk_id`, ключі збігаються з мігрованими, `sync_state` на місці → інкремент продовжується без baseline. Рядки `WK_TOKEN__*` і `TG_FORUM_CHAT_ID` з `shared/env` прибрати (їх більше ніхто не читає). Форум — `/setup` у ньому (§6).
