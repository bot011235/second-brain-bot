"""Регистрация Telegram Webhook и кнопки меню 'Каталог' (Telegram Mini App) после деплоя на Cloud Run.

Использование:
    python scripts/set_webhook.py https://your-service-xyz.run.app
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings  # noqa: E402


def configure_webhook_and_menu(public_base_url: str | None = None) -> None:
    base_url = (public_base_url or settings.public_base_url).strip().rstrip("/")
    if not base_url or not base_url.startswith("https://"):
        print("ОШИБКА: Укажите публичный HTTPS URL сервиса (аргументом или в PUBLIC_BASE_URL в .env)")
        sys.exit(1)
    if not settings.telegram_bot_token:
        print("ОШИБКА: Укажите TELEGRAM_BOT_TOKEN в .env")
        sys.exit(1)

    tg_api = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
    webhook_url = f"{base_url}/webhook/telegram"
    tma_url = f"{base_url}/tma/"

    with httpx.Client(timeout=20.0) as client:
        wh_payload = {
            "url": webhook_url,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": False,
        }
        if settings.telegram_webhook_secret:
            wh_payload["secret_token"] = settings.telegram_webhook_secret

        r_wh = client.post(f"{tg_api}/setWebhook", json=wh_payload).json()
        print(f"Webhook ({webhook_url}): {r_wh}")

        r_menu = client.post(
            f"{tg_api}/setChatMenuButton",
            json={
                "menu_button": {
                    "type": "web_app",
                    "text": "Каталог",
                    "web_app": {"url": tma_url},
                }
            },
        ).json()
        print(f"Кнопка меню 'Каталог' ({tma_url}): {r_menu}")


if __name__ == "__main__":
    arg_url = sys.argv[1] if len(sys.argv) > 1 else None
    configure_webhook_and_menu(arg_url)
