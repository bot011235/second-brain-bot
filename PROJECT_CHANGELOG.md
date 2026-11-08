# Журнал изменений и чек-лист проекта (`PROJECT_CHANGELOG.md`)

> **ВАЖНО ДЛЯ AI-АГЕНТОВ (ВО ВСЕХ ЧАТАХ ПРОЕКТА):**
> Перед началом любой работы прочитайте этот файл, чтобы знать актуальное состояние архитектуры, облачного деплоя и всех правок из соседних чатов.
> После внесения любых изменений в код, базу данных или деплой **обязательно допишите новую запись** в раздел «Хронология изменений» и при необходимости обновите облако (`git push` в GitHub + триггер деплоя на Render).

---

## 1. Текущая инфраструктура и окружение (Production)

- **Telegram-группа (форум)**: `Notes📎` (`TG_CHAT_ID = -1003531389022`), владелец `ALLOWED_TG_USER_ID = 349407845`.
  - Топики: `General` (`None`), `Movies` (`3`), `Books` (`14`), `Ideas` (`5`).
  - Закреплённая кнопка каталога в `General`: `message_id = 203`.
- **Telegram-бот**: `@Alfred_DBv01_bot` (работает через облачный Webhook 24/7).
- **Облачная база данных (Turso / libSQL)**:
  - URL: `libsql://second-brain-vlad2582.aws-eu-central-1.turso.io` (регион Frankfurt, классический SQLite + `FTS5`).
  - Клиент: `TursoHttpConnection` в `app/db/client.py` (работает поверх HTTP Pipeline API `/v2/pipeline` без необходимости компиляции C/Rust-зависимостей на Windows и в Docker).
- **Облачный хостинг (Render.com Free Docker Web Service)**:
  - Публичный URL сервиса: **`https://second-brain-bot-4wcq.onrender.com`**
  - Витрина Telegram Mini App / Web: **`https://second-brain-bot-4wcq.onrender.com/tma/`**
  - Telegram Webhook URL: **`https://second-brain-bot-4wcq.onrender.com/webhook/telegram`**
  - Render Service ID: `srv-dbnmpuqjnfac73cqn5mg` (привязан к GitHub-репозиторию `https://github.com/bot011235/second-brain-bot`, ветка `main`).
- **Подключённые внешние API**:
  - **Кино/Сериалы (100% официальные источники)**: TMDB API (`api.themoviedb.org`), Wikidata SPARQL/Entity API (`P345` IMDb, `P2603` Кинопоиск, `P1258` Rotten Tomatoes), официальный XML-рейтинг Кинопоиска (`https://rating.kinopoisk.ru/{kp_id}.xml`), парсер Tomatometer (`rottentomatoes.com`), прямая поисковая ссылка на КП даже при отсутствии `kp_id`.
  - **Книги**: Google Books API, Русская Википедия + Wikidata (с автоисправлением опечаток вроде `гипперион` → `Гиперион`), FantLab API (`api.fantlab.ru`), Goodreads (рейтинг и ссылка), OpenLibrary.
  - **LLM (Groq)**: модели `openai/gpt-oss-120b` (основная), `openai/gpt-oss-20b` и `qwen/qwen3.8-27b` (fallback).
  - **Скрапер ссылок и постов**: YouTube Data API / oEmbed (`app/clients/youtube.py`), OpenGraph + Jina Reader / JSON-LD фолбэк для Threads/Instagram и веб-статей (`app/clients/scraper.py`).

---

## 2. Чек-лист готовности этапов

- [x] **Этап 0**: Спецификация v2 (`telegram_turso_tma.md`), отказ от неофициальных API, настройка `.env`.
- [x] **Этап 1**: База данных (`001_init.sql`, `002_originals.sql`), миграции, FTS5-индекс, дедупликация, единый обработчик `app/bot/handlers.py`.
- [x] **Этап 2**: Пайплайн фильмов и сериалов (TMDB + Wikidata + КП XML + Rotten Tomatoes + кликабельные ссылки прямо на цифрах рейтингов в HTML-карточке).
- [x] **Этап 3**: Пайплайн книг (Google Books + Википедия/Wikidata + FantLab + Goodreads + пакетная отправка списком по строкам).
- [x] **Этап 4**: Пайплайн ссылок, видео, статей, постов Threads/Instagram (с извлечением полного текста поста и автора) и авто-извлечением списков фильмов/книг через Groq LLM.
- [x] **Этап 5**: Интерактивные кнопки статусов (`В планах`, `В процессе`, `Готово`, `Брошено`), разрешение неоднозначностей (`needs_choice`), удаление карточек.
- [x] **Этап 6**: Витрина Telegram Mini App (`app/tma/`) — светлая тема, пастельные карточки по категориям, оценка без `/10`, компактная строка жанров/тегов по убыванию популярности с выпадающим списком `Ещё жанры/теги...`, переключатель режимов **«🗂 Каталог» / «📝 Оригиналы»** (`/api/originals`).
- [x] **Этап 7**: Read-only MCP сервер (`mcp_server/server.py`), скрипт бэкапов (`scripts/backup.py`), синхронизация с Turso (`scripts/sync_local_to_turso.py`), облачный деплой на Render (`scripts/deploy_render.py`).

---

## 3. Хронология изменений (Лог правок по всем чатам)

### 2026-11-07 — Архив «Оригиналы» и улучшенный разбор Threads/Instagram + КП ссылки
- **База данных (`app/db/migrations/002_originals.sql`, `app/db/repo.py`)**:
  - Добавлена таблица `original_messages` для сохранения всех исходных сообщений пользователя (`raw_text`, `topic_slug`, `source_url`, `source_type`, `author`, `extracted_text`, `created_at`) с автоматическим бэкфиллом из существующих `items`.
  - В `repo.py` добавлены `create_original_message` и `list_original_messages` (с фильтрацией по топику и поиском по тексту/автору/ссылке).
- **Скрапер и обработчики (`app/clients/scraper.py`, `app/bot/handlers.py`, `app/clients/groq_llm.py`, `app/utils/urls.py`)**:
  - Улучшено извлечение текста и автора из постов Threads/Instagram (разбор JSON-LD, очистка заголовков `Threads`/`Instagram`, фолбэк для закрытых страниц).
  - Очистка трекинговых параметров `xmt` и `slof` в `app/utils/urls.py`.
  - Каждое входящее сообщение теперь автоматически логируется в `original_messages` через `_record_original_message`.
  - Карточки статей/постов/видео не выводят кино-рейтинг КП (`app/bot/cards.py`, `app/tma/app.js`), а для фильмов/сериалов без `kp_id` формируется поисковая ссылка на Кинопоиск (`kp_query=...`).
- **Витрина TMA (`app/main.py`, `app/tma/index.html`, `app/tma/app.js`, `app/tma/styles.css`)**:
  - Добавлен эндпоинт `GET /api/originals` и переключатель **«🗂 Каталог» / «📝 Оригиналы»** в шапке витрины.
  - Открыт доступ к чтению и управлению витриной как внутри Telegram Mini App (`initData`), так и напрямую по ссылке в браузере.

### 2026-11-07 — Переезд в облако Turso + Render и кнопка «Каталог»
- **Turso Cloud DB (`app/db/client.py`, `scripts/sync_local_to_turso.py`)**:
  - Реализован `TursoHttpConnection` поверх HTTP API Turso (`/v2/pipeline`).
  - Локальная база синхронизирована с кластером `libsql://second-brain-vlad2582.aws-eu-central-1.turso.io`.
- **Render Cloud Deployment (`Dockerfile`, `scripts/deploy_render.py`, `scripts/set_webhook.py`)**:
  - Код опубликован в `https://github.com/bot011235/second-brain-bot` и развёрнут в Render (`https://second-brain-bot-4wcq.onrender.com`).
  - Настроен Telegram Webhook и кнопка меню бота «Каталог», а также закреплена кнопка «🗂 Открыть Каталог» в топике `General` группы `Notes📎`.
