"""Автоматическая отправка коммитов в GitHub и запуск деплоя на Render (использует ключи из .env).

Запуск из любого чата проекта:
    python scripts/push_and_deploy.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent

ENV_VARS_TO_SYNC = [
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
    "GOOGLE_BOOKS_API_KEY",
    "YOUTUBE_API_KEY",
    "PUBLIC_BASE_URL",
    "WEB_ACCESS_KEY",
    "WEB_ADMIN_USERNAME",
    "WEB_ADMIN_PASSWORD",
]


def load_env_map() -> dict[str, str]:
    env_map: dict[str, str] = {}
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return env_map
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            env_map[k.strip()] = v.strip()
    return env_map


def main() -> None:
    env_map = load_env_map()
    gh_token = env_map.get("GITHUB_TOKEN", "")
    render_key = env_map.get("RENDER_API_KEY", "")
    service_id = env_map.get("RENDER_SERVICE_ID", "srv-dbnmpuqjnfac73cqn5mg")

    if not gh_token:
        print("❌ Ошибка: В .env не найден GITHUB_TOKEN")
        sys.exit(1)

    remote_url = f"https://bot011235:{gh_token}@github.com/bot011235/second-brain-bot.git"
    print("1️⃣ Отправляю git push в GitHub...")
    subprocess.run(["git", "push", remote_url, "main"], cwd=str(ROOT), check=True)
    print("   ✅ Код успешно отправлен в GitHub (main).")

    if not render_key:
        print("⚠️ RENDER_API_KEY не задан, пропускаю триггер Render API.")
        return

    headers = {
        "Authorization": f"Bearer {render_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=30.0, headers=headers) as client:
        # 2. Синхронизируем переменные окружения (.env -> Render), включая GOOGLE_BOOKS_API_KEY, YOUTUBE_API_KEY, PUBLIC_BASE_URL
        env_payload = [
            {"key": k, "value": env_map[k]}
            for k in ENV_VARS_TO_SYNC
            if env_map.get(k)
        ]
        r_env = client.put(
            f"https://api.render.com/v1/services/{service_id}/env-vars",
            json=env_payload,
        )
        if r_env.status_code == 200:
            print(f"2️⃣ Синхронизированы переменные окружения в Render ({len(env_payload)} шт.).")

        # 3. Запускаем деплой
        r_dep = client.post(
            f"https://api.render.com/v1/services/{service_id}/deploys",
            json={},
        )
        print(f"3️⃣ Запущен деплой на Render: {r_dep.status_code} {r_dep.text}")


if __name__ == "__main__":
    main()
