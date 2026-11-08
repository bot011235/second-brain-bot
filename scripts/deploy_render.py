from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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
    "PUBLIC_BASE_URL",
]


def deploy_render(render_token: str, repo_url: str) -> None:
    headers = {
        "Authorization": f"Bearer {render_token.strip()}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    env_map = {}
    env_path = Path(__file__).resolve().parent.parent / ".env"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            env_map[k.strip()] = v.strip()

    env_vars = [{"key": k, "value": env_map[k]} for k in SECRETS_KEYS if env_map.get(k)]

    with httpx.Client(timeout=30.0, headers=headers) as client:
        owners = client.get("https://api.render.com/v1/owners")
        owners.raise_for_status()
        owner_id = owners.json()[0]["owner"]["id"]
        print(f"👤 Render Workspace ID: {owner_id}")

        # Проверим, нет ли уже созданного сервиса
        existing = client.get("https://api.render.com/v1/services")
        if existing.status_code == 200:
            for item in existing.json():
                svc = item.get("service", {})
                if svc.get("name") == "second-brain-bot":
                    print(f"ℹ️ Сервис уже существует: {svc.get('id')} ({svc.get('serviceDetails', {}).get('url')})")
                    return

        payload = {
            "type": "web_service",
            "name": "second-brain-bot",
            "ownerId": owner_id,
            "repo": repo_url,
            "branch": "main",
            "autoDeploy": "yes",
            "envVars": env_vars,
            "serviceDetails": {
                "runtime": "docker",
                "plan": "free",
                "region": "frankfurt",
                "healthCheckPath": "/healthz",
            },
        }
        r = client.post("https://api.render.com/v1/services", json=payload)
        print("Render response:", r.status_code, r.text)


if __name__ == "__main__":
    deploy_render(sys.argv[1], sys.argv[2])
