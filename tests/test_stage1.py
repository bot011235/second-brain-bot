from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bot.handlers import handle_update
from app.config import settings
from app.db.client import get_connection
from app.db.migrate import apply_migrations
from app.db.repo import get_item
from app.utils.normalize import normalize_text


class DummyTelegramClient:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.edited: list[dict[str, Any]] = []
        self.deleted: list[int] = []

    def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        message_thread_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.sent.append(
            {"chat_id": chat_id, "text": text, "thread_id": message_thread_id, "reply_markup": reply_markup}
        )
        return {"ok": True, "result": {"message_id": 999}}

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.edited.append({"chat_id": chat_id, "message_id": message_id, "text": text, "reply_markup": reply_markup})
        return {"ok": True}

    def delete_message(self, chat_id: int, message_id: int) -> dict[str, Any]:
        self.deleted.append(message_id)
        return {"ok": True}

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> dict[str, Any]:
        return {"ok": True}


class TestStage1(unittest.TestCase):
    def test_normalize_cyrillic_and_yo(self) -> None:
        self.assertEqual(normalize_text("  Ёжик в тумане! (1975) "), "ежик в тумане 1975")
        self.assertEqual(normalize_text("The Matrix: Reloaded"), "matrix reloaded")

    def test_stage1_end_to_end_pipeline(self) -> None:
        conn = get_connection(":memory:")
        apply_migrations(conn)

        settings.tg_chat_id = -100111
        settings.allowed_tg_user_id = 42
        settings.topic_ideas_id = 10
        settings.telegram_bot_token = "dummy:token"

        tg = DummyTelegramClient()
        upd = {
            "update_id": 1001,
            "message": {
                "message_id": 55,
                "message_thread_id": 10,
                "chat": {"id": -100111},
                "from": {"id": 42},
                "text": "Заметка про архитектуру",
            },
        }

        res = handle_update(conn, upd, tg=tg)  # type: ignore[arg-type]
        self.assertEqual(res["status"], "created")
        item_id = res["item_id"]
        self.assertEqual(res["category"], "idea")
        self.assertEqual(len(tg.sent), 1)
        self.assertEqual(tg.deleted, [55])

        # Повторный webhook с тем же update_id игнорируется (идемпотентность)
        dup = handle_update(conn, upd, tg=tg)  # type: ignore[arg-type]
        self.assertEqual(dup["status"], "duplicate_update")

        # Проверка FTS5 по кириллице
        fts_rows = conn.execute("SELECT rowid FROM items_fts WHERE items_fts MATCH 'архитектуру'").fetchall()
        self.assertEqual(len(fts_rows), 1)
        self.assertEqual(fts_rows[0][0], item_id)

        # Смена статуса кнопкой
        cb_upd = {
            "update_id": 1002,
            "callback_query": {
                "id": "cb1",
                "from": {"id": 42},
                "message": {"message_id": 999, "chat": {"id": -100111}},
                "data": f"st:{item_id}:planned",
            },
        }
        cb_res = handle_update(conn, cb_upd, tg=tg)  # type: ignore[arg-type]
        self.assertEqual(cb_res["status"], "status_updated")
        item = get_item(conn, item_id)
        assert item is not None
        self.assertEqual(item["status"], "planned")
        self.assertEqual(len(tg.edited), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
