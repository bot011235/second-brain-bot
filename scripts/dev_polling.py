"""Скрипт для локальной разработки (long polling) и обнаружения ID чата/топиков.

Режим 1 — Обнаружение ID (Этап 0):
    uv run python scripts/dev_polling.py --discover

Режим 2 — Полноценная обработка сообщений и кнопок (Этап 1+):
    uv run python scripts/dev_polling.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.bot.handlers import handle_update  # noqa: E402
from app.config import settings  # noqa: E402
from app.db.client import get_connection  # noqa: E402
from app.db.migrate import apply_migrations  # noqa: E402


def poll(discover_only: bool = False, once: bool = False) -> None:
    if not settings.telegram_bot_token:
        print("ОШИБКА: Укажите TELEGRAM_BOT_TOKEN в файле .env")
        sys.exit(1)

    if not discover_only:
        applied = apply_migrations()
        if applied:
            print(f"Применены миграции: {applied}")

    base = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
    with httpx.Client(timeout=40.0) as client:
        client.post(f"{base}/deleteWebhook")
        me = client.get(f"{base}/getMe").json()
        if not me.get("ok"):
            print(f"ОШИБКА токена бота: {me}")
            sys.exit(1)
        bot_user = me["result"].get("username")
        mode_str = "DISCOVER (только вывод ID)" if discover_only else "PIPELINE (создание карточек в БД)"
        print(f"Бот @{bot_user} запущен в режиме {mode_str}.")

        offset = 0
        while True:
            try:
                resp = client.get(
                    f"{base}/getUpdates",
                    params={
                        "offset": offset,
                        "timeout": 2 if once else 30,
                        "allowed_updates": ["message", "callback_query"],
                    },
                ).json()
                updates = resp.get("result", [])
                if once and not updates:
                    print("Новых сообщений в очереди пока нет.")
                for upd in updates:
                    offset = upd["update_id"] + 1
                    msg = upd.get("message")
                    if msg:
                        chat_id = msg.get("chat", {}).get("id")
                        chat_title = msg.get("chat", {}).get("title")
                        user_id = msg.get("from", {}).get("id")
                        thread_id = msg.get("message_thread_id")
                        topic_created = (msg.get("forum_topic_created") or {}).get("name")
                        reply_topic = ((msg.get("reply_to_message") or {}).get("forum_topic_created") or {}).get("name")
                        text = msg.get("text") or msg.get("caption") or f"<service: {topic_created or 'msg'}>"
                        topic_name = settings.resolve_topic_name(thread_id)
                        print(
                            f"[update_id={upd['update_id']}] "
                            f"chat={chat_title!r} (TG_CHAT_ID={chat_id}) | ALLOWED_TG_USER_ID={user_id} | "
                            f"message_thread_id={thread_id} (topic_title={reply_topic or topic_created!r}, mapped='{topic_name}') | text={text!r}"
                        )
                    if not discover_only:
                        conn = get_connection()
                        try:
                            res = handle_update(conn, upd)
                            print(f"  -> результат: {res}")
                        finally:
                            conn.close()
                if once:
                    if offset:
                        client.get(f"{base}/getUpdates", params={"offset": offset, "timeout": 0})
                    break
            except KeyboardInterrupt:
                print("\nОстановлено.")
                break
            except Exception as exc:
                print(f"Ошибка опроса: {exc}")
                if once:
                    if offset:
                        client.get(f"{base}/getUpdates", params={"offset": offset, "timeout": 0})
                    break
                time.sleep(3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--discover", action="store_true", help="Только выводить ID чата, пользователя и топиков")
    parser.add_argument("--once", action="store_true", help="Проверить очередь обновлений один раз и выйти")
    args = parser.parse_args()
    poll(discover_only=args.discover, once=args.once)
