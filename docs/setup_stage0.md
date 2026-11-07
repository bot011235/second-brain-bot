# Инструкция по Этапу 0: Ключи, аккаунты и ID топиков

## 1. Скопируйте шаблон `.env`
```powershell
Copy-Item .env.example .env
```

## 2. Где получить бесплатные ключи ($0)
1. **Telegram Bot (`TELEGRAM_BOT_TOKEN`):**
   - Откройте `@BotFather` → `/newbot` → скопируйте токен.
   - Создайте закрытую группу, включите в ней **Topics (Темы)**, создайте топики: `Movies`, `Books`, `Ideas`, `YouTube`, `Articles` (топик `General` уже есть).
   - Добавьте бота в группу и назначьте **Администратором** с правами: *Delete messages* (Удаление сообщений) и *Manage topics* (Управление темами).
2. **Узнать `TG_CHAT_ID`, `ALLOWED_TG_USER_ID` и ID всех топиков:**
   - Впишите `TELEGRAM_BOT_TOKEN` в `.env`.
   - Запустите:
     ```powershell
     uv run python scripts/dev_polling.py --discover
     ```
   - Отправьте по одному сообщению в каждый топик (`Movies`, `Books`, `Ideas`, `YouTube`, `Articles`, `General`).
   - В консоли появятся точные значения `TG_CHAT_ID`, `ALLOWED_TG_USER_ID` и `message_thread_id` для каждого топика — перенесите их в `.env`.
3. **Turso (`TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`):**
   - Зарегистрируйтесь на `https://turso.tech` (Starter Plan — бесплатно без карты).
   - Создайте базу `second-brain` через веб-панель или CLI (`turso db create second-brain`), скопируйте URL (`libsql://...`) и создайте токен (`turso db tokens create second-brain`).
4. **Groq (`GROQ_API_KEY`):**
   - `https://console.groq.com/keys` → Create API Key (бесплатно без карты).
5. **Kinopoisk Unofficial (`KINOPOISK_API_KEY`):**
   - `https://kinopoiskapiunofficial.tech` → регистрация → скопируйте API-ключ из профиля (500 запросов/сутки бесплатно).
6. **OMDb (`OMDB_API_KEY`):**
   - `https://www.omdbapi.com/apikey.aspx` → выберите **FREE! (1,000 daily limit)** → подтвердите ключ по ссылке из письма.
7. **Google Cloud (`YOUTUBE_API_KEY`, `GOOGLE_BOOKS_API_KEY`) — без привязки карты:**
   - В Google Cloud Console создайте проект (`New Project` в верхней панели, **без активации платного триала и без привязки карты**).
   - Включите **YouTube Data API v3** (и при желании **Books API**) в *APIs & Services → Library*.
   - В *Credentials* создайте API Key (`Public data`) и пропишите его в `YOUTUBE_API_KEY` и `GOOGLE_BOOKS_API_KEY`.
8. **Хостинг контейнера (Этап 5):**
   - Развёртывание **вообще без карты и залогов** — на **Render.com** (Free Web Service из `Dockerfile`) или **Hugging Face Spaces** (Docker Space).
