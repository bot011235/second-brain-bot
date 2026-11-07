from __future__ import annotations

import os
from pathlib import Path
from pydantic import BaseModel


def _load_dotenv(env_path: str = ".env") -> None:
    path = Path(env_path)
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        os.environ.setdefault(key, val)


_load_dotenv()


def _env_int(name: str, default: int = 0) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


class Settings(BaseModel):
    # Telegram
    telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_webhook_secret: str = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    tg_chat_id: int = _env_int("TG_CHAT_ID", 0)
    allowed_tg_user_id: int = _env_int("ALLOWED_TG_USER_ID", 0)

    # Topic IDs (0 = not configured yet)
    topic_movies_id: int = _env_int("TOPIC_MOVIES_ID", 0)
    topic_books_id: int = _env_int("TOPIC_BOOKS_ID", 0)
    topic_ideas_id: int = _env_int("TOPIC_IDEAS_ID", 0)
    topic_youtube_id: int = _env_int("TOPIC_YOUTUBE_ID", 0)
    topic_articles_id: int = _env_int("TOPIC_ARTICLES_ID", 0)

    # Turso
    turso_database_url: str = os.environ.get("TURSO_DATABASE_URL", "")
    turso_auth_token: str = os.environ.get("TURSO_AUTH_TOKEN", "")
    local_db_path: str = os.environ.get("LOCAL_DB_PATH", "data/second_brain.db")

    # Groq
    groq_api_key: str = os.environ.get("GROQ_API_KEY", "")
    groq_model: str = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
    groq_fallback_model: str = os.environ.get("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")
    llm_for_ideas: bool = _env_bool("LLM_FOR_IDEAS", True)

    # Media APIs (official)
    tmdb_api_key: str = os.environ.get("TMDB_API_KEY", "")
    google_books_api_key: str = os.environ.get("GOOGLE_BOOKS_API_KEY", "")
    youtube_api_key: str = os.environ.get("YOUTUBE_API_KEY", "")

    # Deployment
    public_base_url: str = os.environ.get("PUBLIC_BASE_URL", "")

    def resolve_topic_name(self, thread_id: int | None) -> str:
        """Сопоставляет message_thread_id с именем топика."""
        if thread_id is None:
            return "general"
        mapping = {
            self.topic_movies_id: "movies",
            self.topic_books_id: "books",
            self.topic_ideas_id: "ideas",
            self.topic_youtube_id: "youtube",
            self.topic_articles_id: "articles",
        }
        mapping.pop(0, None)
        return mapping.get(thread_id, "general")


settings = Settings()
