# T33 · Зміст повідомлень: підсумок сесії, блоки статистики, карта рівнів à la wkstats, діфи

`2026-09-13` · 💡 proposal

Контекст:
- твій запит 2026-09-13: після сесії — статистика (скільки уроків і які, ревʼю, помилки, успіхи), «красиво»; карта прогресу як у wkstats (поточний стан, сортування, два рівні групування, фільтри) і порядок рівнів як в Android-застосунку (лише apprentice, найкоротші/найперші, з мінімальних рівнів або у зворотному); головне — бачити **що змінилося**: попередній і наступний стан поруч або прихована цитата з переліком змін; усе це — налаштовуване, щоб «гратися»;
- дані: `events` (T01; точність часу — [T31](T31-C--session-gap-analysis.md) §1), поточні `assignments` / `subjects` / `summaries`; оформлення — [T07](T07-P--bot-vision.md) §7 (Telegram HTML, `<blockquote expandable>`, спойлери), палітра стадій `STAGE_EMOJI` у `digest.py`;
- модель нотифікацій і сесій — [T32](T32-P--notifications-model.md); UX налаштувань — [T34](T34-P--settings-ux-layers.md); варіанти рендеру — [T35](T35-B--sessions-alternatives.md) §3, §6.

## 1. Статистика вікна (`Stats` з подій — сесія, доба, тиждень одним кодом)

Чиста функція `window_stats(events, subjects) -> Stats`:
- **ревʼю:** айтемів `n` (Σ `meta.count`), ✅ `ok` (жодної помилки), ❌ `bad`; точність по айтемах `ok / n`; по відповідях: правильних = `n` (meaning) + `n_kanji_vocab` (reading), помилок = Σ `meaning_wrong + reading_wrong` → `answers_acc`; помилки за типом відповіді (meaning / reading — «сиплюсь на читаннях»);
- **за типом предмета:** R / K / V / KV — `n` і ❌; **за рівнем:** `n` і ❌ на рівень («на яких рівнях сиплюсь»);
- **SRS:** ⬆️ / ⬇️; переходи між групами: `→ Guru +3`, `→ Master +1`, `→ Enlightened +2`, `🔥 Burned +1`; пул Apprentice було → стало (з `reverse_apply`, §3.1);
- **уроки:** `started` `n` + список; **розблокування:** `unlocked`;
- **віхи:** level-up, `passed` (перший Guru), burned, resurrected, reset;
- **час:** перший → останній момент, тривалість, темп (айтемів/хв), найдовша пауза;
- **черга:** `due` до / після (`assignments` з `available_at ≤ now`, стадія 1–8; збігається з `summary.reviews_now` ±4) → «📉 due 4058 → 4038»;
- **проблемні:** айтеми з ❌ і `percentage_correct < 75` → «🩹 leeches»; найдовша серія ✅ у сесії;
- **порівняння** (`compare`, L2): з попередньою сесією / середнім за 7 днів — `n`, точність, тривалість.

## 2. Підсумок сесії — рендер (Telegram HTML)

Дефолт (`detail: normal`, `items: wrong`):
```
🧘 Vitalik · session 17:52–18:05 (13 min)
20 reviews · ✅ 15 ❌ 5 · 75% (answers 84%) · 1.5/min
⬆️ 12 ⬇️ 4 · → Guru 3 · 🔥 1 · 📖 3 lessons
📉 due 4058 → 4038 · 🩷 apprentice 102 → 98

❌ wrong (5)                        ← <blockquote expandable>
  漢 · Chinese (K12) · A3 → A1 (m1)
  語 · language (V5) · G1 → A4 (r2)
  …
🔥 burned: 一 · one (K1)
📖 lessons: 新しい · new, 古い · old, 高い · tall

🗺 what changed                     ← <blockquote expandable>
  L37 🩷 5→3 · 💜 12→14
  L38 🩷 20→18 · 💙 3→4 · 🔥 +1
```
- Рядки 1–4 — блок `header`, завжди; далі блоки за налаштуваннями; довгі списки — у `<blockquote expandable>` (згорнуто, розгортається тапом — це і є «прихована цитата»); лінки на предмети як у `digest.py`.
- `detail: compact` — лише header; `full` — усі айтеми (✅ теж), повна карта замість діфу.
- **Живе** повідомлення під час сесії — той самий рендер із `· live` замість тривалості й без важких блоків (карта, порівняння) — вони зʼявляються на закритті.
- Блоки за замовчуванням і порядок: `header` · `moves` (переходи списком) · `wrong` · `wins` (burned / passed / level) · `lessons` · `changes` (діф карти) · `leeches` (off) · `compare` (off) · `all_items` (off) · `map` (повна карта, off).
- Денний / тижневий: той самий рендер над вікном + рядок `sessions: 3 · 41 min · best 90%` + `changes` за вікно + (пізніше) стрік; `hourly` — header + wrong.
- Лише уроки: `📖 Vitalik · lessons 21:00–21:12 · 15 started` + список; без рядка точності.

## 3. Карта прогресу (à la wkstats)

### 3.1 Дані

- Стан предмета для акаунта: `locked` (нема assignment) · `lesson` (stage 0, розблоковано) · `apprentice` 1–4 · `guru` 5–6 · `master` 7 · `enlightened` 8 · `burned` 9; окремо `due` (available_at ≤ now, 1–8).
- Матриця `level → type → stage → n` з `assignments` (≈9 400 предметів, одна агрегація) + `subjects` для `locked`; межа — `max_level_granted` (у тебе 60), `hidden` не рахуються.
- **«Що змінилось»** — `reverse_apply(matrix_now, events_window)`: `srs_up/down` (`from → to`), `unlocked` (locked → lesson), `resurrected` (burned → stage) — дає точну матрицю «до» для будь-якого вікна без снапшотів і без реплею історії; `started` уже покритий `srs_up 0→1`. Перевірка — тест проти реплею `history` (T32 §8). Альтернативи — [T35](T35-B--sessions-alternatives.md) §3.
- Перелік змін по айтемах (для цитати) — з тих самих подій, згруповано за рівнем: `L37: 漢 A3→A1 ⬇️, 語 G1→G2`.

### 3.2 Опції (спільні для `/progress` і блоків `changes` / `map`)

- `levels`: `around` (current−N … current, дефолт N=5) · `all` · `range a–b` · `ahead` (current … current+M — що попереду, розблокування);
- `group`: `level` (дефолт) · `stage` · `type`; `then`: `none` · `type` — два рівні групування («рівень → тип», «стадія → рівень»);
- `sort`: `asc` · `desc` · `current_first` (поточний, далі вниз);
- `filter`: `all` · `apprentice` · `due` · `not_burned` · `leeches` · `changed` (лише рівні зі змінами у вікні);
- `style`: `emoji` (смуга з емодзі стадій) · `counts` (числа) · `both`;
- `diff`: `off` · `inline` (`5→3`) · `before_after` (дві смуги) · базове вікно `session | day | week | since <дата>`;
- `due`: on/off — колонка «⏳ due» на рівень.

### 3.3 Рендер

Emoji-смуга: 10 клітинок = частки предметів рівня в порядку 🔒 🩷 💜 💙 🩵 🔥 (locked → burned), `⏳` due:
```
🗺 Vitalik · L39 · levels 34–39 ↑ · Δ session
L34 🩷💜💜💜💜💙💙🩵🔥🔥 · ⏳12 · 🩷 5→3
L35 🩷🩷💜💜💜💜💙💙🔥🔥 · ⏳9
L36 🩷🩷🩷💜💜💜💜💙💙🔥 · ⏳14 · 💜 +2
L37 🩷🩷🩷🩷💜💜💜💜💙💙 · ⏳20 · 🩷 5→3 · 💜 12→14
L38 🔒🩷🩷🩷🩷💜💜💜💜💙 · ⏳18 · 🔥 +1
L39 🔒🔒🔒🩷🩷🩷🩷💜💜💜 · ⏳31 · 🩷 20→18
```
Числа (`style: counts`, у `<code>` для вирівнювання):
```
L34  🔒0  🩷5  💜40  💙35  🩵20  🔥52  ⏳12
```
- Емодзі однакової ширини в усіх клієнтах Telegram — смуга тримає форму; діф справа лише для змінених груп.
- `group: stage` — рядок на групу стадій зі списком рівнів: `🩷 Apprentice 102 (−4): L39 20→18 · L37 5→3 · …` — це режим «концентруюсь на apprentice».
- `diff: before_after` — дві смуги під рівнем («було / стало») — наочно, але вдвічі довше; лише для `around` з малим N.
- Обмеження Telegram 4096 символів → `_chunk` як у `digest.py`; `all` рівнів → 60 рядків × ~40 символів — влазить в одне повідомлення в `emoji`, у `both` — два.
- PNG (Pillow, палітра wkstats) — крок «потім»: ті самі `level_rows` → картинка; бот шле фото з підписом ([T35](T35-B--sessions-alternatives.md) §6).

### 3.4 `/progress` — інтерактивно (приват і група)

```
🗺 Vitalik · L39 · levels 34–39 ↑ · Δ session
…рядки…
[↑ asc] [↓ desc] [🎯 current first]
[levels: 34–39 ▸] [group: level ▸] [filter: all ▸]
[style: emoji ▸] [Δ: session ▸] [🔄]
[👤 2vitalik] [📌 Use in 🧘 Session] [🧹 Close]
```
- Кожна кнопка перерендерює те саме повідомлення; `▸` — цикл значень; `levels` цикл `around 3 · around 5 · around 10 · all · ahead 3`; діапазон руками — L3.
- Опції зберігаються в `tg_users.prefs.progress[account]` — наступний `/progress` відкривається так, як ти залишив; `📌 Use in 🧘 Session` копіює їх у блок `changes`/`map` обраної нотифікації (той самий обʼєкт опцій, T34 §2).
- Кілька акаунтів — перемикач `👤`; у групі — свій акаунт того, хто натиснув, `🧹 Close`.

## 4. Код рендеру

- `ReportContext` (чистий): `account, label, tz, window (start, end), events, stats: Stats, matrix_after, matrix_before, changed_items, subjects, due (before, after), session | None, compare | None`.
- `render/blocks.py`: `BLOCKS = {name: fn(ctx, opts) -> list[str] | None}` — `None` = порожній блок, не показувати; `render/report.py`: `compose(ctx, blocks_order, opts) -> list[str]` з chunking; `render/progress.py`: `level_rows(matrix, before, opts) -> list[str]`, `stage_groups(...)`.
- `Stats` і матриця — у `lib` (`stats.py`, `progress.py`), щоб CLI (`wklabs report`), `/status` і майбутній web рахували одним кодом (T07 §6).
- i18n — не зараз, але тексти блоків живуть окремими функціями, локалізація потім не болить.

## 5. Мотиваційні дрібниці (➕ мої, усе — опційні блоки)

- `📉 due` як тренд у daily (`4058 → 3840 за тиждень`) і «best session this week» (точність / кількість); `pace` до наступного рівня з `level_progressions` («L39 day 12 · avg 19») — блок `pace` (off у сесії, on у daily).
- Одне речення похвали `tone: plain | cheerful` (L2, дефолт plain): «🔥 first burn on L38». Без потоку конфеті.
- Стрік — після daily ([T07](T07-P--bot-vision.md) §1), мʼякий (`14 days · 1 skip`).

## Твої думки та питання

> 
