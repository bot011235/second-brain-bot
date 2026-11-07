from __future__ import annotations

from typing import Any

import httpx

from app.config import settings


class TelegramClient:
    """Тонкий синхронный клиент Telegram Bot API поверх httpx."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token or settings.telegram_bot_token
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        clean = {k: v for k, v in payload.items() if v is not None}
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(f"{self.base_url}/{method}", json=clean)
            return resp.json()

    def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        message_thread_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        has_poster_preview = "&#8205;</a>" in text
        return self._post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "message_thread_id": message_thread_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": not has_poster_preview,
                "reply_markup": reply_markup,
            },
        )

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        has_poster_preview = "&#8205;</a>" in text
        return self._post(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": not has_poster_preview,
                "reply_markup": reply_markup,
            },
        )

    def delete_message(self, chat_id: int, message_id: int) -> dict[str, Any]:
        return self._post("deleteMessage", {"chat_id": chat_id, "message_id": message_id})

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> dict[str, Any]:
        return self._post("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})
