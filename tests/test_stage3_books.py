from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bot.handlers import handle_update
from app.config import settings
from app.db.client import get_connection
from app.db.migrate import apply_migrations
from app.db.repo import get_item


class FakeBooksClient:
    def search_candidates(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        return [
            {
                "source": "google_books",
                "category": "book",
                "google_books_id": "gb_heidegger_1",
                "title_ru": "Бытие и время",
                "title_orig": None,
                "creator": "Мартин Хайдеггер",
                "release_year": 1927,
                "summary": "Фундаментальный труд по экзистенциальной онтологии.",
                "poster_url": "https://books.google.com/books/content?id=gb_heidegger_1&printsec=frontcover&img=1",
                "isbn13": "9785936150241",
                "genres": ["philosophy"],
                "page_count": 460,
                "info_link": "https://books.google.com/books?id=gb_heidegger_1",
            },
            {
                "source": "google_books",
                "category": "book",
                "google_books_id": "gb_heidegger_2",
                "title_ru": "Введение в метафизику",
                "title_orig": None,
                "creator": "Мартин Хайдеггер",
                "release_year": 1953,
                "summary": "Курс лекций 1935 года.",
                "poster_url": None,
                "isbn13": None,
                "genres": ["philosophy"],
                "page_count": 300,
                "info_link": "https://books.google.com/books?id=gb_heidegger_2",
            },
        ]


class DummyTG:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.edited: list[dict[str, Any]] = []
        self.deleted: list[int] = []

    def send_message(self, chat_id: int, text: str, **kwargs: Any) -> dict[str, Any]:
        self.sent.append({"chat_id": chat_id, "text": text, **kwargs})
        return {"ok": True, "result": {"message_id": 700 + len(self.sent)}}

    def edit_message_text(self, chat_id: int, message_id: int, text: str, **kwargs: Any) -> dict[str, Any]:
        self.edited.append({"chat_id": chat_id, "message_id": message_id, "text": text, **kwargs})
        return {"ok": True}

    def delete_message(self, chat_id: int, message_id: int) -> dict[str, Any]:
        self.deleted.append(message_id)
        return {"ok": True}

    def set_message_reaction(self, chat_id: int, message_id: int, emoji: str = "👍") -> dict[str, Any]:
        return {"ok": True}

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> dict[str, Any]:
        return {"ok": True}


class TestStage3Books(unittest.TestCase):
    @patch("app.pipeline.books.fetch_goodreads_info")
    @patch("app.pipeline.books.fetch_fantlab_info")
    def test_book_exact_and_dedup(self, mock_fl: Any, mock_gr: Any) -> None:
        mock_fl.return_value = {
            "fantlab_id": 1,
            "rating_fantlab": 8.56,
            "url_fantlab": "https://fantlab.ru/work1",
            "summary": None,
        }
        mock_gr.return_value = {
            "rating_goodreads": 4.44,
            "url_goodreads": "https://www.goodreads.com/book/show/3943",
        }
        conn = get_connection(":memory:")
        apply_migrations(conn)

        settings.tg_chat_id = -1003531389022
        settings.allowed_tg_user_id = 349407845
        settings.topic_books_id = 14
        settings.telegram_bot_token = "dummy:token"

        tg = DummyTG()
        books_client = FakeBooksClient()

        # 1. Запрос с автором и названием -> однозначное совпадение (автовыбор)
        upd1 = {
            "update_id": 3001,
            "message": {
                "message_id": 20,
                "message_thread_id": 14,
                "chat": {"id": -1003531389022},
                "from": {"id": 349407845},
                "text": "Мартин Хайдеггер Бытие и время",
            },
        }
        res1 = handle_update(conn, upd1, tg=tg, books_client=books_client)  # type: ignore[arg-type]
        self.assertEqual(res1["status"], "created")
        item_id = res1["item_id"]

        item = get_item(conn, item_id)
        assert item is not None
        self.assertEqual(item["category"], "book")
        self.assertEqual(item["google_books_id"], "gb_heidegger_1")
        self.assertEqual(item["creator"], "Мартин Хайдеггер")

        # 2. Повторная отправка той же книги -> дедупликация
        upd2 = {
            "update_id": 3002,
            "message": {
                "message_id": 21,
                "message_thread_id": 14,
                "chat": {"id": -1003531389022},
                "from": {"id": 349407845},
                "text": "Мартин Хайдеггер Бытие и время",
            },
        }
        res2 = handle_update(conn, upd2, tg=tg, books_client=books_client)  # type: ignore[arg-type]
        self.assertEqual(res2["status"], "duplicate_item")
        self.assertEqual(res2["item_id"], item_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
