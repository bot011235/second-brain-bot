# Архитектура и Техническое Задание: Персональная система «Второй мозг» и Медиа-каталог

## 1. Суть проекта и разделение контуров (Data Segregation)

Система решает проблему хаотичного сохранения ссылок (Threads, Instagram, YouTube, статьи) и текстовых заметок (фильмы, сериалы, книги, идеи) с телефона и ПК, обеспечивая автоматическое обогащение данных (рейтинги, описания), дедупликацию, наглядный визуальный каталог и готовность базы для подключения ИИ (RAG / MCP). Cost = **$0/мес**.

### Разделение данных на 2 независимых контура:
1. **Приватный контур (Sensitive Info / Документы / Личные заметки из `Important`):**
   * **Инструмент:** **Anytype** (приложения на Android и ПК).
   * **Безопасность:** Local-first архитектура с End-to-End шифрованием (`AES-256`) на устройстве по seed-фразе из 12 слов (Zero-Knowledge).
   * **Синхронизация ($0):** Безлимитно для текста/объектов через облако Anytype + до 1 ГБ для тяжелых файлов в облаке + безлимитная P2P-синхронизация файлов напрямую между телефоном и ноутбуком в локальной Wi-Fi сети.
2. **Публичный и медиа-контур (Фильмы, Сериалы, Книги, Посты Threads/Instagram, YouTube, Идеи):**
   * **Точка входа (Inbox):** Закрытая Telegram-группа с топиками (`Movies`, `Books`, `Ideas`, `General` и др.).
   * **Обработчик (Backend):** Serverless Python-сервис (Webhook).
   * **База данных (Storage & AI Ready):** **Turso (libSQL)** в облаке + локальная синхронизируемая реплика `SQLite` на ПК.
   * **Визуальная витрина (Frontend):** Карточки в Telegram (HTML / HTMLBubbles) + **Telegram Mini App (TMA)** для фильтрации и сортировки каталога как на сайте.

---

## 2. Стек технологий и бесплатные лимиты ($0 Budget)

| Компонент | Выбранное решение | Роль в системе | Условия Free Tier |
| :--- | :--- | :--- | :--- |
| **Backend / Webhook** | **Google Cloud Run** *(или Vercel / Cloudflare Workers)* | Прием вебхуков от Telegram, запуск Python-логики (FastAPI / Flask), вызов внешних API, запись в БД. | Google Cloud Run: 2 млн запросов/мес бесплатно (требует привязки карты для верификации аккаунта, но деньги не списываются в рамках лимита). *Если без привязки карты — Vercel / Cloudflare Workers.* |
| **LLM (Парсинг смысла)** | **Groq API** (`console.groq.com`) | Извлечение названия фильма/книги или краткой сути (summary) и тегов из сырого текста поста Threads/Instagram/YouTube. | **100% бесплатно в ЕС без привязки карты.** Модели: `llama-3.3-70b-versatile`, `qwen/qwen3-32b`. До 1 000–14 400 запросов/сутки. |
| **База данных** | **Turso (libSQL / SQLite)** (`turso.tech`) | Облачное хранение всех записей + встроенный векторный поиск (`F32_BLOB`) для ИИ + локальный файл `.db` на ноутбуке. | **Бесплатно без карты:** 5 ГБ хранилища, 500 млн чтений и 10 млн записей в месяц. |
| **Кино / Сериалы API** | **OMDb API** + **Kinopoisk Unofficial API** | Получение `imdb_id`, `kp_id`, постера, года, жанров, описания и 3 рейтингов (**IMDb**, **Rotten Tomatoes**, **Кинопоиск**). | OMDb: 1 000 запросов/сутки бесплатно. Kinopoisk Unofficial: 500 запросов/сутки бесплатно. |
| **Книги API** | **Google Books API** / OpenLibrary API | Получение автора, года, обложки, описания и ISBN. | Бесплатно (1 000 запросов/сутки). |
| **Витрина (Frontend)** | **Telegram Mini App (TMA)** | Одностраничное веб-приложение (HTML/CSS/JS) внутри Telegram с галереей постеров, поиском, фильтрами по жанрам и сортировкой по рейтингам. | Бесплатный хостинг статики на **Cloudflare Pages** или **GitHub Pages** (или раздача прямо из FastAPI на Cloud Run). |

---

## 3. Схема работы пайплайна (User Flow & Logic)

### Шаг 1. Захват информации (Ingestion)
Пользователь с телефона или ПК отправляет в нужный топик Telegram-группы `Notes`:
* Ссылку (например, пост из Threads, рилс из Instagram, видео с YouTube, ссылку на сайт);
* Или просто текст (например, `Разделение` или `Хайдеггер Бытие и время`).

### Шаг 2. Перехват и классификация (Webhook & AI)
1. Telegram мгновенно отправляет `POST`-запрос (Webhook) в сервис на **Google Cloud Run**.
2. Скрипт считывает `message_thread_id` (определяя топик: `Movies`, `Books`, `Ideas` и т.д.), текст сообщения и URL.
3. Если внутри ссылка (Threads / Instagram / YouTube / статья):
   * Скрипт забирает метаданные страницы (OpenGraph теги: `og:title`, `og:description`, `og:image` или текст через легкий скрапер / `yt-dlp` метаданные).
   * Отправляет извлеченный текст в **Groq API** с системным промптом: вернуть строгий JSON (`entity_type`, `canonical_title`, `original_title`, `year`, `author_or_director`, `summary`, `tags`).

### Шаг 3. Проверка на дубликаты (Deduplication)
До создания новой карточки скрипт проверяет базу **Turso**:
1. **По точному URL:** Есть ли уже этот URL в массиве `source_urls`.
2. **По каноническому идентификатору (для фильмов и книг):**
   * Для `Movies` скрипт делает поиск в OMDb / Kinopoisk API и получает уникальные `imdb_id` (например, `tt11280740`) и `kp_id`.
   * Проверяет в таблице `items`: существует ли запись с таким `imdb_id` или связкой `normalized_title + year`.
3. **Логика при обнаружении дубликата:**
   * Новая запись в БД **не создается**.
   * В существующую запись в поле `sources` добавляется новая ссылка (откуда еще раз посоветовали этот фильм/книгу).
   * Бот удаляет новое сообщение пользователя и отвечает в чат уведомлением со ссылкой на уже существующую карточку (либо обновляет существующее сообщение в Telegram).

### Шаг 4. Обогащение данных (Enrichment)
* **Если категория `Movies`:**
  1. Запрос в **OMDb API** по названию/году или `imdb_id`: забираем рейтинг `imdbRating`, рейтинг `Rotten Tomatoes` (из массива `Ratings`), постер, жанры.
  2. Запрос в **Kinopoisk Unofficial API**: забираем `ratingKinopoisk`, `kinopoiskId`, русское название и описание.
  3. Формируются 3 прямые ссылки:
     * Кинопоиск: `https://www.kinopoisk.ru/film/{kp_id}/`
     * IMDb: `https://www.imdb.com/title/{imdb_id}/`
     * Rotten Tomatoes: прямая ссылка из OMDb (`tomatoURL`) или поисковый редирект `https://www.rottentomatoes.com/search?search={urlencoded_original_title}`.
* **Если категория `Books`:**
  * Запрос в **Google Books API**: забираем автора, обложку, описание, количество страниц и категории.
* **Если категория `Ideas` / `General` (Посты, YouTube):**
  * Сохраняются чистый заголовок, выжимка сути (Summary от Groq), теги, превью-картинка и оригинальная ссылка.

### Шаг 5. Сохранение и ответ в Telegram
1. Запись сохраняется в базу **Turso**.
2. Бот удаляет «сырое» сообщение пользователя в топике и отправляет на его место отформатированную карточку (`parse_mode="HTML"` или `HTMLBubbles` с интерактивными кнопками).

---

## 4. Схема базы данных (Turso / SQLite)

Единая гибкая структура таблиц, готовая для фильтрации в каталоге и работы в качестве RAG («Второго мозга») для ИИ:

```sql
-- Основная таблица всех единиц контента
CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,              -- 'movie', 'series', 'book', 'post', 'video', 'idea'
    status TEXT DEFAULT 'inbox',         -- 'inbox', 'planned', 'watching', 'completed', 'dropped'
    
    -- Канонические названия и идентификаторы для защиты от дублей
    title_ru TEXT,
    title_orig TEXT,
    normalized_title TEXT NOT NULL,      -- нижний регистр без спецсимволов для быстрого поиска
    release_year INTEGER,
    imdb_id TEXT UNIQUE,                 -- например, 'tt11280740' (защита от дублей кино)
    kp_id INTEGER UNIQUE,                -- ID Кинопоиска
    isbn TEXT UNIQUE,                    -- для книг
    
    -- Рейтинги (для сортировки в каталоге)
    rating_imdb REAL,                    -- 8.7
    rating_kp REAL,                      -- 8.2
    rating_rt INTEGER,                   -- 97 (в процентах)
    user_rating INTEGER,                 -- личная оценка (1-10)
    
    -- Контент и описание
    summary TEXT,                        -- описание фильма/книги или суть поста от LLM
    creator TEXT,                        -- режиссер, автор книги или автор канала/поста
    poster_url TEXT,                     -- ссылка на постер или обложку
    
    -- Прямые ссылки на сервисы
    url_kp TEXT,
    url_imdb TEXT,
    url_rt TEXT,
    
    -- Связь с Telegram
    tg_chat_id INTEGER,
    tg_topic_id INTEGER,
    tg_message_id INTEGER,               -- ID сообщения карточки в ТГ для редактирования
    
    -- Поле под векторный поиск (Второй мозг / RAG в Turso)
    embedding F32_BLOB(768),             -- опционально для семантического поиска
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Таблица источников (один фильм/книга может иметь несколько ссылок из Threads/Insta)
CREATE TABLE item_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    source_url TEXT NOT NULL UNIQUE,     -- ссылка на конкретный пост в Threads / YouTube
    source_type TEXT,                    -- 'threads', 'instagram', 'youtube', 'web', 'manual'
    raw_text TEXT,                       -- исходный текст поста для полнотекстового поиска
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

-- Таблица тегов и жанров (для фильтрации в Mini App)
CREATE TABLE item_tags (
    item_id INTEGER NOT NULL,
    tag TEXT NOT NULL,                   -- 'триллер', 'фантастика', 'ai', 'аналитика'
    PRIMARY KEY (item_id, tag),
    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
);

-- Индексы для мгновенной сортировки и фильтрации на телефоне
CREATE INDEX idx_items_category ON items(category);
CREATE INDEX idx_items_status ON items(status);
CREATE INDEX idx_items_rating_imdb ON items(rating_imdb DESC);
CREATE INDEX idx_items_rating_kp ON items(rating_kp DESC);
```

---

## 5. Спецификация интерфейса: Telegram Mini App (Витрина)

Чтобы удобно просматривать базу с телефона и ПК как полноценный сайт:

1. **Точка входа:** Кнопка `Каталог` в меню бота или закрепленная Inline-кнопка в топиках.
2. **Авторизация и безопасность:**
   * При открытии Mini App передает на бэкенд `window.Telegram.WebApp.initData`.
   * Бэкенд проверяет криптографическую подпись HMAC-SHA256 через токен бота и сверяет `user.id` с белым списком (`ALLOWED_TG_USER_ID`). Посторонний человек открыть каталог не может.
3. **Функционал экрана:**
   * **Табы категорий сверху:** `Все` | `🎬 Кино и Сериалы` | `📚 Книги` | `💡 Посты и Видео`.
   * **Панель управления:**
     * Поиск по тексту (название, описание, автор).
     * Фильтр по жанрам/тегам (выпадающий список или чипсы: `Триллер`, `Детектив`, `AI` и т.д.).
     * Фильтр по статусу (`Хочу посмотреть` / `Просмотрено`).
     * Сортировка: `По IMDb ↓`, `По Кинопоиску ↓`, `По Rotten Tomatoes ↓`, `По дате добавления ↓`.
   * **Карточка элемента:**
     * Постер / обложка, название (RU / Orig), год, жанры.
     * Бейджи рейтингов с цветовой индикацией (`IMDb`, `КП`, `RT`).
     * Сворачиваемое описание.
     * Кнопки быстрых переходов: `[КП]`, `[IMDb]`, `[RT]` + ссылки на исходные посты в Threads/Instagram, откуда была сохранена рекомендация.
     * Кнопка смены статуса в 1 тап: `✅ Отметить просмотренным / прочитанным`.

---

## 6. Интеграция со «Вторым мозгом» (AI / RAG / MCP)

Так как все данные нормализованы и лежат в **Turso (SQLite)**, база данных сразу готова к использованию с любыми ИИ-инструментами:
1. **Локальная синхронизация на ПК:** На ноутбуке настраивается Embedded Replica (или скрипт синхронизации), который держит актуальную копию файла `second_brain.db`.
2. **Подключение через MCP (Model Context Protocol):** В Google Antigravity, Claude Desktop, Cursor или VS Code подключается стандартный `mcp-server-sqlite` с путем к `second_brain.db`. ИИ получает прямой доступ к таблицам `items`, `item_sources` и `item_tags` и может отвечать на сложные запросы по твоей личной базе знаний.
3. **Векторный и полнотекстовый поиск (FTS5):** В SQLite включается виртуальная таблица `FTS5` по полям `title_ru`, `title_orig`, `summary`, `raw_text`, что позволяет ИИ мгновенно находить сохраненные полгода назад посты из Threads или YouTube по смыслу и ключевым словам.

---

## 7. Пошаговый план разработки для Google Antigravity

При переносе проекта в Antigravity разработку рекомендуется вести итерациями (по промптам):

* **Этап 1 (Инфраструктура и БД):** Создать базу в Turso (`turso db create second-brain`), получить `TURSO_DATABASE_URL` и `TURSO_AUTH_TOKEN`. Написать скрипт инициализации таблиц (`schema.sql`).
* **Этап 2 (Модуль парсинга и обогащения):** Написать Python-модули:
  * `scraper.py` — извлечение текста и OpenGraph из URL (Threads, Instagram, YouTube).
  * `llm_parser.py` — интеграция с **Groq API** для классификации и извлечения JSON-структуры из сырого текста.
  * `media_enricher.py` — клиенты для **OMDb API**, **Kinopoisk Unofficial API** и **Google Books API** + логика проверки дублей по `imdb_id` / `kp_id` / `normalized_title`.
* **Этап 3 (Telegram Webhook Bot):** Обернуть логику в **FastAPI** приложение, настроить эндпоинт `/webhook/telegram`, генерацию красивого HTML-шаблона карточки и деплой контейнера в **Google Cloud Run**.
* **Этап 4 (Telegram Mini App):** Сгенерировать одностраничный фронтенд (HTML + TailwindCSS + Alpine.js/Vanilla JS) с API-эндпоинтами `/api/items` (с поддержкой query-параметров фильтрации и сортировки) и проверкой `Telegram.WebApp.initData`.