from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import settings

SECRETS_KEYS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
    "TG_CHAT_ID",
    "ALLOWED_TG_USER_ID",
    "TOPIC_MOVIES_ID",
    "TOPIC_BOOKS_ID",
    "TOPIC_IDEAS_ID",
    "TURSO_DATABASE_URL",
    "TURSO_AUTH_TOKEN",
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "GROQ_FALLBACK_MODEL",
    "LLM_FOR_IDEAS",
    "TMDB_API_KEY",
]


def deploy_hf(token: str) -> None:
    headers = {"Authorization": f"Bearer {token.strip()}"}
    with httpx.Client(timeout=30.0, headers=headers) as client:
        me = client.get("https://huggingface.co/api/whoami-v2")
        me.raise_for_status()
        username = me.json()["name"]
        space_name = "second-brain"
        repo_id = f"{username}/{space_name}"
        print(f"👤 Аккаунт Hugging Face: {username}")

        # 1. Создаём Space (Docker SDK, публичный HTTPS роутинг, секреты скрыты)
        create_payload = {
            "type": "space",
            "name": space_name,
            "sdk": "docker",
            "private": False,
        }
        r = client.post("https://huggingface.co/api/repos/create", json=create_payload)
        if r.status_code not in (200, 201, 409):
            print("Ответ создания Space:", r.status_code, r.text)
            r.raise_for_status()
        print(f"✅ Space готов: https://huggingface.co/spaces/{repo_id}")

        # 2. Прописываем секреты из .env
        env_map = {}
        env_path = Path(__file__).resolve().parent.parent / ".env"
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                env_map[k.strip()] = v.strip()

        for key in SECRETS_KEYS:
            val = env_map.get(key, "")
            if not val:
                continue
            sr = client.post(
                f"https://huggingface.co/api/spaces/{repo_id}/secrets",
                json={"key": key, "value": val},
            )
            if sr.status_code not in (200, 201):
                print(f"⚠️ Не удалось установить секрет {key}: {sr.status_code} {sr.text}")
        print("🔐 Все секреты из .env загружены в защищённое хранилище Space!")

        host_url = f"https://{username}-{space_name}.hf.space".lower()
        client.post(
            f"https://huggingface.co/api/spaces/{repo_id}/secrets",
            json={"key": "PUBLIC_BASE_URL", "value": host_url},
        )
        print(f"🌐 Публичный HTTPS URL сервиса: {host_url}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python scripts/deploy_hf_space.py <HF_WRITE_TOKEN>")
        sys.exit(1)
    deploy_hf(sys.argv[1])
