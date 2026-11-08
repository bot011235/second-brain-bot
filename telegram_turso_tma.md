# Архитектура и ТЗ: Персональная система «Второй мозг» и Медиа-каталог — v2

> **Статус:** зафиксировано 2026-11-07. Предыдущая версия — [docs/archive/telegram_turso_tma_v1.md](docs/archive/telegram_turso_tma_v1.md).
> Все изменения относительно v1 и причины — в разделе [11. Журнал решений](#11-журнал-решений).

---

## 1. Суть проекта и разделение контуров

Система решает проблему хаотичного сохранения ссылок (Threads, Instagram, YouTube, статьи) и текстовых заметок (фильмы, сериалы, книги, идеи) с телефона и ПК: автоматическое обогащение (рейтинги, описания), дедупликация, визуальный каталог и готовность базы для ИИ (MCP, позже RAG). **Бюджет: \$0/мес.** Пользователь — **один** (владелец).

### Контуры данных
1. **Приватный контур** (документы, пароли, чувствительные заметки) — **отложен**, инструмент будет выбран позже.
   * Anytype отклонён: мобильное приложение неудобное (низкий рейтинг в Google Play, слабый UX).
   * Кандидаты на будущее: **Notesnook** (заметки, E2E), **Obsidian** + Remotely Save / Obsidian Sync, **Bitwarden / Proton Pass** (секреты), **Proton Drive** (сканы).
   * Вне кода проекта.
   > ⚠️ **Правило по умолчанию:** всё, что попадает в бота, **считается несекретным**. Данные проходят через Telegram, Groq и Turso без E2E-шифрования, поэтому пароли, номера документов и сканы в группу не отправлять.
2. **Медиа-контур** (кино, сериалы, книги, YouTube, статьи, посты, идеи) — **предмет этого проекта**:
   * **Inbox:** закрытая Telegram-группа с топиками.
   * **Backend:** Python (FastAPI) в Docker-контейнере на **Render.com** (Free Web Service без привязки карты), webhook.
   * **БД:** **Turso (libSQL)** + локальная embedded-реплика на ПК.
   * **Витрина:** карточки в Telegram (`parse_mode="HTML"` + inline-кнопки) и **Telegram Mini App (TMA)**.

---

## 2. Стек и бесплатные лимиты

| Компонент | Решение | Роль | Free tier / заметки |
| :--- | :--- | :--- | :--- |
| **Backend** | **Render.com** (Docker Web Service, Python 3.12, FastAPI) | Webhook Telegram, API для TMA, раздача статики TMA | **100% бесплатно без привязки карты** (0 PLN). Запускает существующий `Dockerfile` напрямую. 750 бесплатных часов в месяц. |
| **БД** | **Turso (libSQL)** | Хранение, FTS5, позже векторы | 5 ГБ, 500 млн rows read, 10 млн rows written в месяц. Полные сканы съедают rows read, поэтому нужны индексы. |
| **Кино: поиск и метаданные** | **TMDB API** (`themoviedb.org`) + **Wikidata API** | Официальный поиск по-русски и в оригинале, описание, жанры, постер, год, тип (фильм/сериал), `imdb_id`, `kp_id` (`P2603`), Rotten Tomatoes ID (`P1258`) | 100% официально и бесплатно. Если ключ TMDB не задан — резервный поиск через Wikidata. |
| **Кино: рейтинги КП и IMDb** | **`rating.kinopoisk.ru/{kp_id}.xml`** | Официальный XML-виджет Кинопоиска: отдаёт `<kp_rating>` и `<imdb_rating>` по `kp_id` | Бесплатно, без ключей и сторонних сайтов. |
| **Книги** | **Google Books API** (резерв — OpenLibrary) | Автор, год, обложка, описание, страницы, категории | Бесплатно. |
| **YouTube** | **YouTube Data API v3** + oEmbed | Заголовок, описание, канал, теги, превью, длительность | 10 000 единиц квоты/сутки (`videos.list` = 1 единица). Ключ из того же GCP-проекта. |
| **Статьи** | `httpx` + **trafilatura** | Извлечение заголовка, текста, автора, даты | Локальная библиотека. |
| **Посты (Threads/Instagram)** | OG-теги (best effort) | `og:title`, `og:description`, `og:image` | Instagram с облачных IP часто отдаёт login wall, тогда бот переходит в сценарий `needs_input`. |
| **LLM** | **Groq API** | Извлечение названий из постов, summary, теги | `llama-3.3-70b-versatile`: ~1 000 запросов и **~100K токенов в сутки** (реальный лимит). Модель и запасная модель задаются в конфиге. |
| **TMA** | Vanilla JS + Alpine.js (CDN), CSS на theme-переменных Telegram | Каталог | Раздаётся тем же FastAPI (без CORS и отдельного хостинга). |

---

## 3. Топики группы и маршрутизация

Топики сопоставляются по **`message_thread_id` из конфига**, а не по названию. У топика **General нет `message_thread_id`** (`None` → General).

| Топик | Вход | Результат (`category`) | LLM |
| :--- | :--- | :--- | :--- |
| **Movies** | Название (`Разделение`, `Дюна 2021`) или ссылка на пост/видео с рекомендацией | `movie` / `series` (тип определяется по Кинопоиску) | Только для ссылок (извлечь список названий) |
| **Books** | Название/автор или ссылка | `book` | Только для ссылок |
| **YouTube** | Ссылка на видео | `video` | Summary + теги |
| **Articles** | Ссылка на статью | `article` | Summary + теги |
| **Ideas** | Свободный текст | `idea` | Заголовок + теги (отключается флагом `LLM_FOR_IDEAS=false`) |
| **General** | Ссылка Threads/Instagram/прочее → `post`; ссылка YouTube → `video`; статья → `article`; текст без ссылки → `idea` | авто | Summary + теги |

> Топик задаёт **намерение**: YouTube-видео «топ-5 фильмов», отправленное в **Movies**, превращается в 5 карточек фильмов (источник у всех — это видео). То же видео, отправленное в **YouTube**, сохраняется как само видео.

---

## 4. Пайплайн обработки

### 4.1. Приём (webhook)
1. Telegram → `POST /webhook/telegram`. Проверяем заголовок `X-Telegram-Bot-Api-Secret-Token`.
2. Фильтр: `chat.id == TG_CHAT_ID` и `from.id == ALLOWED_TG_USER_ID`, иначе игнор (ответ 200).
3. **Идемпотентность:** `INSERT OR IGNORE INTO processed_updates(update_id)`. Если запись уже есть — ответ 200, апдейт не обрабатываем.
4. Сырой ввод сохраняется сразу (`processing_status='pending'`, `raw_input`).
5. **Обработка синхронно внутри запроса** (Cloud Run замораживает CPU после ответа, поэтому `BackgroundTasks` не используем). Таймаут сервиса — 60 с.
6. **На любую ошибку отвечаем Telegram 200** (иначе он будет повторять апдейт). Запись помечается `failed`, бот публикует карточку ошибки с кнопкой `🔄 Повторить`.

### 4.2. Нормализация URL (до любых запросов)
* Удалить `utm_*`, `igsh`, `igshid`, `si`, `feature`, `fbclid` и другие трекинговые параметры, а также `#fragment`.
* `youtu.be/ID`, `youtube.com/shorts/ID`, `m.youtube.com` → `https://www.youtube.com/watch?v=ID`.
* `threads.net` → `threads.com`; убрать `m.` и `www.`, где это безопасно.
* Результат: `canonical_url`, по которому делается дедупликация.

### 4.3. Movies
1. **Текст без ссылки:** LLM не вызывается. Год в конце (`Дюна 2021`) выделяется регуляркой. Запрос → Kinopoisk search.
2. **Ссылка:** scraper → текст → Groq → JSON-список `[{title, original_title?, year?}]` → по каждому элементу поиск в Kinopoisk.
3. **Выбор кандидата:**
   * **Автовыбор**, только если результат один или ровно один кандидат точно совпал по `normalized_title` (и году, если он указан).
   * Иначе — карточка выбора: до **3 кандидатов** inline-кнопками (название, год, тип) + `❌ Ничего не подходит`. Запись в статусе `needs_choice`, кандидаты лежат в `meta`.
   * `❌ Ничего не подходит` → статус `needs_input`, бот просит уточнить (реплаем: название + год или ссылку на КП/IMDb).
4. **После идентификации (`kp_id` известен):**
   * **Дедупликация** по `kp_id` / `imdb_id`. Если запись уже есть — см. 4.8.
   * Kinopoisk details: `nameRu`, `nameOriginal`, `year`, `description`, `ratingKinopoisk`, `imdbId`, жанры, тип (`FILM` → `movie`; `TV_SERIES`/`MINI_SERIES`/`TV_SHOW` → `series`), постер.
   * OMDb `?i={imdb_id}`: `imdbRating`, Rotten Tomatoes из `Ratings`, `tomatoURL` (если есть).
   * Ссылки: КП и IMDb **строятся из ID на лету**. RT — `tomatoURL` или поиск `https://www.rottentomatoes.com/search?search={title_orig}`.

### 4.4. Books
Текст/ссылка → (LLM только для ссылок) → Google Books search → тот же UX выбора кандидата → дедупликация по `google_books_id`, затем по `normalized_title + normalized_creator`. ISBN хранится справочно, **не как уникальный ключ** (у разных изданий разные ISBN).

### 4.5. YouTube
`canonical_url` → дедупликация → `videos.list` (snippet, contentDetails) → Groq: summary (2–4 предложения, RU) + теги → `video`. Превью `i.ytimg.com` стабильные, храним ссылкой.

### 4.6. Articles
`canonical_url` → дедупликация → `httpx` GET → trafilatura (title, text, author, date) + `og:image` → Groq summary + теги → `article`.

### 4.7. Посты (Threads / Instagram / прочее) и Ideas
* **Посты:** OG-теги. Если текста нет (login wall) → статус `needs_input`: бот публикует черновую карточку и просит реплаем прислать текст поста или суть.
* **Картинки постов** (подписанные CDN-ссылки протухают через несколько дней): картинка скачивается и **отправляется в Telegram как фото карточки**. В БД сохраняется `poster_tg_file_id`, TMA получает её через `GET /api/media/{item_id}` (прокси через `getFile`).
* **Ideas:** текст сохраняется как есть, Groq генерирует короткий заголовок и теги.

### 4.8. Дубликат найден
* Новая запись в `items` **не создаётся**. В `item_sources` добавляется источник (если такой пары `item_id + source_url` ещё нет).
* Существующая карточка редактируется (счётчик источников +1, ссылка на новый источник).
* Сообщение пользователя удаляется. Бот отвечает реплаем на существующую карточку: `🔁 Уже в базе — источник добавлен`. Это уведомление удаляется при обработке следующего апдейта (ID последнего уведомления хранится в `bot_state`).

### 4.9. Карточка в Telegram
* Сообщение пользователя **удаляется**, вместо него публикуется карточка (сырой текст хранится в БД).
* Есть картинка → `sendPhoto` с HTML-подписью (**≤ 1024 символа**, описание обрезается); нет картинки → `sendMessage`.
* Содержимое: эмодзи категории, название RU / Orig, год, тип, жанры, бейджи `IMDb 8.7 · КП 8.2 · RT 97%`, короткое описание, теги.
* Кнопки:
  * URL-кнопки: `[КП] [IMDb] [RT] [Источник]`;
  * callback-кнопки: `📌 В планы` · `▶️ В процессе` · `✅ Готово` · `🗑 Удалить` (`callback_data` ≤ 64 байт, формат `st:{item_id}:{status}`).
* Изменения из TMA синхронизируются с карточкой через `editMessageCaption` / `editMessageText`.

---

## 5. Схема базы данных (Turso / libSQL)

> `PRAGMA foreign_keys = ON;` выполняется при каждом подключении. Миграции — пронумерованные SQL-файлы (`migrations/001_init.sql`, …) + таблица `schema_migrations`.

```sql
-- Основная таблица единиц контента
CREATE TABLE items (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    category           TEXT NOT NULL CHECK (category IN ('movie','series','book','video','article','post','idea')),
    status             TEXT NOT NULL DEFAULT 'inbox'
                       CHECK (status IN ('inbox','planned','in_progress','done','dropped')),
    processing_status  TEXT NOT NULL DEFAULT 'pending'
                       CHECK (processing_status IN ('pending','ok','needs_choice','needs_input','failed')),
    processing_error   TEXT,

    -- Названия (normalized_* считаются в Python: casefold, ё→е, без пунктуации)
    title_ru           TEXT,
    title_orig         TEXT,
    normalized_title   TEXT NOT NULL,
    release_year       INTEGER,
    creator            TEXT,                -- режиссёр / автор книги / канал / автор поста
    normalized_creator TEXT,

    -- Канонические идентификаторы (UNIQUE допускает много NULL)
    imdb_id            TEXT UNIQUE,
    kp_id              INTEGER UNIQUE,
    google_books_id    TEXT UNIQUE,
    isbn13             TEXT,                -- справочно, не для дедупа
    canonical_url      TEXT UNIQUE,         -- для video / article / post: URL самого контента

    -- Рейтинги
    rating_imdb        REAL,
    rating_kp          REAL,
    rating_rt          INTEGER,             -- проценты
    user_rating        INTEGER CHECK (user_rating BETWEEN 1 AND 10),

    -- Контент
    summary            TEXT,                -- описание фильма/книги или выжимка поста от LLM
    poster_url         TEXT,                -- стабильные URL (КП, OMDb, Google Books, ytimg)
    poster_tg_file_id  TEXT,                -- для протухающих картинок (Instagram/Threads)
    url_rt             TEXT,                -- КП и IMDb ссылки строятся из ID
    meta               TEXT,                -- JSON: длительность, сезоны, страницы, кандидаты при needs_choice и т.п.
    raw_input          TEXT,                -- исходный текст сообщения

    -- Telegram
    tg_topic_id        INTEGER,
    tg_message_id      INTEGER,             -- ID карточки для редактирования

    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Источники: одна запись может иметь много источников, один пост — много записей
CREATE TABLE item_sources (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id       INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    source_url    TEXT,                     -- canonical URL; NULL для ручного текста
    source_type   TEXT NOT NULL CHECK (source_type IN ('threads','instagram','youtube','web','telegram','manual')),
    raw_text      TEXT,                     -- текст поста/описания для FTS
    added_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (item_id, source_url)
);

-- Жанры (из API) и теги (из LLM) — разделены колонкой kind
CREATE TABLE item_tags (
    item_id  INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    kind     TEXT NOT NULL CHECK (kind IN ('genre','tag')),
    tag      TEXT NOT NULL,                 -- нижний регистр, нормализован
    PRIMARY KEY (item_id, kind, tag)
);

-- Идемпотентность вебхука
CREATE TABLE processed_updates (
    update_id     INTEGER PRIMARY KEY,
    processed_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Мелкое состояние бота (ID последнего уведомления о дубле и т.п.)
CREATE TABLE bot_state (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

-- Полнотекстовый поиск (наполняется кодом: rowid = items.id; при изменении записи — delete + insert)
CREATE VIRTUAL TABLE items_fts USING fts5(
    title_ru, title_orig, creator, summary, tags, sources_text,
    tokenize = 'unicode61 remove_diacritics 2'
);

-- Индексы
CREATE INDEX idx_items_dedup        ON items(category, normalized_title, release_year);
CREATE INDEX idx_items_book_dedup   ON items(normalized_title, normalized_creator) WHERE category = 'book';
CREATE INDEX idx_items_cat_status   ON items(category, status);
CREATE INDEX idx_items_created      ON items(created_at DESC);
CREATE INDEX idx_items_rating_imdb  ON items(rating_imdb DESC);
CREATE INDEX idx_items_rating_kp    ON items(rating_kp DESC);
CREATE INDEX idx_items_rating_rt    ON items(rating_rt DESC);
CREATE INDEX idx_items_processing   ON items(processing_status) WHERE processing_status <> 'ok';
CREATE INDEX idx_tags_tag           ON item_tags(kind, tag);
CREATE INDEX idx_sources_item       ON item_sources(item_id);

-- Автообновление updated_at
CREATE TRIGGER trg_items_updated_at
AFTER UPDATE ON items FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE items SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
```

**Отложено до этапа 7 (эмбеддинги):**
```sql
CREATE TABLE item_embeddings (
    item_id  INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    model    TEXT NOT NULL,
    vector   F32_BLOB(768)          -- размерность зависит от выбранной модели
);
CREATE INDEX idx_item_embeddings_vec ON item_embeddings(libsql_vector_idx(vector));
```

> ⚠️ **Проверить на этапе 1:** поддержку FTS5 (и токенайзера `trigram` для поиска по подстроке) в Turso remote. Запасной вариант — поиск по колонкам `normalized_*` через `LIKE`.

---

## 6. Telegram: настройка

* Бот — **админ группы** с правами: удаление сообщений, управление топиками (privacy mode при этом не мешает).
* Webhook: `setWebhook(url, secret_token=TELEGRAM_WEBHOOK_SECRET, allowed_updates=["message","callback_query"], drop_pending_updates=true)`.
* Для локальной разработки — режим **long polling** (`scripts/dev_polling.py`, перед запуском вызывается `deleteWebhook`). Обработчики у polling и webhook общие.
* Кнопка меню бота `Каталог` → Web App URL `https://<public-base-url>/tma/`.
* Удаление сообщений возможно в течение 48 ч, нам этого хватает.

---

## 7. Telegram Mini App (витрина)

### 7.1. Авторизация
* Фронтенд отправляет `Authorization: tma <initData>` с каждым запросом.
* Бэкенд проверяет HMAC-SHA256 (ключ = `HMAC_SHA256("WebAppData", bot_token)`), **свежесть `auth_date`** (≤ 24 ч) и `user.id == ALLOWED_TG_USER_ID`.

### 7.2. API
| Метод | Путь | Назначение |
| :--- | :--- | :--- |
| GET | `/api/items` | Список. Параметры: `category`, `status`, `tag` (повторяемый), `q` (FTS), `sort` (`imdb`/`kp`/`rt`/`user`/`created`), `limit`, `cursor` |
| GET | `/api/items/{id}` | Карточка + источники + теги |
| PATCH | `/api/items/{id}` | `status`, `user_rating` → синхронизация с карточкой в чате |
| DELETE | `/api/items/{id}` | Удаление записи и карточки в чате |
| GET | `/api/tags` | Жанры и теги со счётчиками |
| GET | `/api/media/{id}` | Прокси картинки по `poster_tg_file_id` |

### 7.3. Экран
* **Табы:** `Все` · `🎬 Кино и сериалы` · `📚 Книги` · `▶️ YouTube` · `📰 Статьи` · `💡 Идеи и посты`.
* **Панель:** поиск (FTS), чипсы жанров и тегов, фильтр статуса (подписи зависят от категории: «Хочу посмотреть» / «Хочу прочитать» / «Смотрю» / «Читаю» …), сортировка.
* **Отдельный фильтр «Требуют внимания»** (`needs_choice` / `needs_input` / `failed`).
* **Карточка:** постер, RU / Orig, год, жанры, цветные бейджи рейтингов, сворачиваемое описание, кнопки `[КП] [IMDb] [RT]`, ссылки на источники, «Открыть в чате» (`https://t.me/c/{chat}/{topic}/{msg}`), смена статуса в один тап, личная оценка 1–10.
* Цвета берутся из `Telegram.WebApp.themeParams`, светлая и тёмная темы поддерживаются автоматически.

---

## 8. «Второй мозг»: локальная реплика, MCP, поиск

1. **Локальная реплика (ПК, Windows):** владельцем файла `data/second_brain.db` выступает сам MCP-сервер. Он открывает embedded replica (`libsql.connect(path, sync_url, auth_token)`) и вызывает `sync()` при старте и перед запросами (не чаще раза в N минут). Другие процессы этот файл не открывают.
2. **Свой read-only MCP-сервер** (`mcp_server/`, Python, FastMCP) вместо архивного `mcp-server-sqlite` (тот умеет писать и не знает libSQL-функций). Инструменты:
   * `search_items(query, category?, limit?)` — FTS5;
   * `get_item(id)` — запись + источники + теги;
   * `list_items(filters…)`;
   * `run_select(sql)` — только `SELECT`, с лимитом строк.
   Подключается к Antigravity / Claude Desktop / Cursor.
3. **Бэкапы:** `scripts/backup.py` — ежедневный SQL-dump с ротацией (7 ежедневных + 4 еженедельных) в `backups/` (Планировщик задач Windows).
4. **Семантический поиск** — этап 7. Источник эмбеддингов выберем тогда (Gemini Embedding API или локальная multilingual-модель).

---

## 9. Структура проекта и конфигурация

```
Personal_DB/
├─ telegram_turso_tma.md        # это ТЗ
├─ docs/archive/                # прошлые версии ТЗ
├─ app/
│  ├─ main.py                   # FastAPI: /webhook/telegram, /api/*, /tma/*, /healthz
│  ├─ config.py                 # pydantic-settings
│  ├─ db/                       # client.py, repo.py, migrate.py, migrations/*.sql
│  ├─ bot/                      # telegram_api.py (тонкий httpx-клиент), handlers.py, cards.py, keyboards.py
│  ├─ pipeline/                 # router.py, movies.py, books.py, youtube.py, articles.py, posts.py, ideas.py, dedup.py
│  ├─ clients/                  # kinopoisk.py, omdb.py, google_books.py, youtube.py, groq_llm.py, scraper.py
│  ├─ utils/                    # normalize.py, urls.py, initdata.py
│  └─ tma/                      # index.html, app.js, styles.css (статика)
├─ mcp_server/server.py
├─ scripts/                     # dev_polling.py, set_webhook.py, backup.py, migrate.py
├─ tests/                       # pytest: нормализация, URL, initData, парсинг ответов API (фикстуры)
├─ Dockerfile
├─ pyproject.toml               # uv
├─ .env.example
└─ .gitignore                   # .env, data/, backups/
```

**Ключевые библиотеки:** `fastapi`, `uvicorn`, `httpx`, `pydantic`, `pydantic-settings`, `libsql`, `groq`, `selectolax` (OG-теги), `trafilatura`, `mcp` (FastMCP), `pytest`.
**Синхронный код** (`def`-эндпоинты, sync `httpx`, sync `libsql`): для одного пользователя async не нужен, а так проще.

**Переменные окружения** (`.env` локально, Environment Variables на **Render.com**):
```
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
TG_CHAT_ID=
ALLOWED_TG_USER_ID=
TOPIC_MOVIES_ID=
TOPIC_BOOKS_ID=
TOPIC_IDEAS_ID=
TOPIC_YOUTUBE_ID=
TOPIC_ARTICLES_ID=
# General = сообщения без message_thread_id
TURSO_DATABASE_URL=
TURSO_AUTH_TOKEN=
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_FALLBACK_MODEL=llama-3.1-8b-instant
LLM_FOR_IDEAS=true
KINOPOISK_API_KEY=
OMDB_API_KEY=
GOOGLE_BOOKS_API_KEY=
YOUTUBE_API_KEY=
PUBLIC_BASE_URL=
LOCAL_DB_PATH=data/second_brain.db
```

**LLM-вызовы:** JSON mode, ответ проверяется Pydantic-моделью; при невалидном ответе — один повтор, затем запасная модель. В промпт тегов передаётся список существующих тегов, чтобы LLM переиспользовал их, а не плодил дубли (`ai` / `ии` / `AI`).

---

## 10. План разработки (итерации)

| Этап | Содержание | Готово, когда |
| :--- | :--- | :--- |
| **0. Подготовка** | Репо, `uv`, структура, `.env.example`. Аккаунты и ключи: BotFather, Turso, Groq, TMDB, Google Cloud (только ключ YouTube Data API v3 / Books API — без карты и биллинга). Группа с топиками, бот — админ, собраны ID топиков | Все ключи в `.env`, `scripts/dev_polling.py` видит сообщения из всех топиков |
| **1. Скелет** | Миграции + схема, FastAPI, webhook и polling, идемпотентность, маршрутизация по топикам, сохранение `raw_input`, простая карточка с заменой сообщения, кнопки статусов. Проверка FTS5 в Turso | Любое сообщение превращается в карточку и запись в БД, кнопки статусов работают |
| **2. Movies** | Kinopoisk → OMDb, нормализация, дедупликация, выбор кандидата, `needs_input`, карточка с рейтингами | `Разделение` → выбор → карточка с IMDb/КП/RT; повторная отправка → «уже в базе» |
| **3. Books** | Google Books (+ OpenLibrary), выбор кандидата, дедупликация | Аналогично Movies |
| **4. Ссылки** | Нормализация URL, YouTube API, trafilatura, OG, Groq (summary/теги/списки названий), перезалив картинок, посты-подборки → N карточек | Ссылки YouTube, статьи и Threads обрабатываются; подборка в Movies даёт N карточек |
| **5. Деплой** | Dockerfile, деплой на **Render.com** (Free Web Service), `setWebhook`, переменные окружения | Бот работает 24/7 без ПК |
| **6. TMA** | API + фронтенд, initData, фильтры, сортировки, синхронизация с карточками | Каталог открывается из меню бота, фильтры и смена статуса работают |
| **7. Второй мозг** | Read-only MCP-сервер с embedded replica, бэкапы, затем эмбеддинги и семантический поиск | MCP отвечает на запросы по базе в Antigravity |

> Этапы 2–4 можно разрабатывать локально в polling-режиме. Деплой (5) делается, когда ядро стабильно, но его можно поднять и раньше.

---

## 11. Журнал решений

| # | Решение | Причина |
| :--- | :--- | :--- |
| D1 | Хостинг — **Render.com** (Free Web Service из Dockerfile) | 100% бесплатно, без карты и залогов; в Google Cloud биллинг закрыт (GCP остаётся только для бесплатного ключа YouTube/Books API без карты) |
| D2 | Кино: **Официальная связка TMDB (`themoviedb.org`) + Wikidata (`P345`/`P2603`/`P1258`) + `rating.kinopoisk.ru/{kp_id}.xml`** | Отказ от неофициальных сайтов (`kinopoiskapiunofficial`, `omdbapi`) в пользу 100% официальных источников |
| D3 | Неоднозначность → **выбор из 2–3 кандидатов кнопками** | Не допускать записей с не тем фильмом |
| D4 | Пост-подборка → **отдельная карточка на каждый фильм/книгу**, источник общий; `UNIQUE(item_id, source_url)` | В v1 `source_url UNIQUE` запрещал такой сценарий |
| D5 | Исходное сообщение **удаляется и заменяется карточкой**, `raw_input` хранится в БД | Чистый топик |
| D6 | Эмбеддинги **отложены на последний этап**, сначала FTS5 | У Groq нет embedding-моделей; ванильный SQLite не знает libSQL-векторов |
| D7 | Топики: **Movies, Books, Ideas, General, YouTube, Articles** | Выбор владельца |
| D8 | Пользователь **один** (`ALLOWED_TG_USER_ID`) | Выбор владельца |
| D9 | Обработка **синхронно внутри webhook-запроса** + идемпотентность по `update_id`; на ошибки — ответ 200 | Cloud Run замораживает CPU после ответа |
| D10 | `HTMLBubbles` убран, используется `parse_mode="HTML"` + `inline_keyboard` | `HTMLBubbles` не существует в Bot API |
| D11 | `yt-dlp` и Instagram-скрапинг убраны; YouTube → Data API v3; Instagram → OG best effort + `needs_input` | Блокировки облачных IP |
| D12 | Протухающие картинки перезаливаются в Telegram (`poster_tg_file_id`) | CDN-ссылки Instagram/Threads живут несколько дней |
| D13 | Нормализация текста в Python, поиск через FTS5 | `lower()` / `LIKE` в SQLite не работают с кириллицей |
| D14 | Статусы `inbox / planned / in_progress / done / dropped`, подписи в UI зависят от категории | `watching` не подходит книгам |
| D15 | Книги: дедупликация по `google_books_id` и `title + author`, ISBN не уникален | У разных изданий разные ISBN |
| D16 | Свой read-only MCP-сервер вместо `mcp-server-sqlite` | Архивный сервер умеет писать и не знает libSQL-функций |
| D17 | TMA раздаётся из того же FastAPI; Alpine.js без сборки | Одна единица деплоя, без CORS |
| D18 | Python 3.12 + `uv`; синхронный код; тонкий httpx-клиент Telegram | Простота для одного пользователя *(допущение — можно изменить)* |
| D19 | Интерфейс только на русском; импорт старого бэклога — опционально после этапа 4 | *Допущения — можно изменить* |
| D20 | **Приватный контур отложен**, Anytype отклонён. Весь проект по умолчанию работает с несекретными данными | Мобильное приложение Anytype неудобное; к секретным данным вернёмся отдельно |
