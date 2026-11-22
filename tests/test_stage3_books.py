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

    def test_parse_book_query_and_relevance_filtering(self) -> None:
        from app.clients.books import BooksClient, _score_book_candidate, _is_relevant_book_candidate, parse_book_query

        self.assertEqual(
            parse_book_query("1. Американский психопат — Брет Истон Эллис (1991)"),
            ("Американский психопат", "Брет Истон Эллис", 1991),
        )
        self.assertEqual(
            parse_book_query("7. Уловка-22 — Джозеф Хеллер (1961)"),
            ("Уловка-22", "Джозеф Хеллер", 1961),
        )
        self.assertEqual(
            parse_book_query("Мартин Хайдеггер Бытие и время"),
            ("Мартин Хайдеггер Бытие и время", None, None),
        )

        # Мусор Google Books отбрасывается
        garbage = {
            "source": "google_books",
            "title_ru": "ТЕЛЕНЕДЕЛЯ для всей семьи. Москва 48",
            "creator": "Редакция журнала",
            "release_year": 2015,
        }
        self.assertFalse(_is_relevant_book_candidate(garbage, "Дерьмо", "Ирвин Уэлш", 1998))

        # Книга 'Лёд (2011)' выигрывает у серии 'Майор Мартен Сервас'
        series_cand = {
            "source": "fantlab",
            "fantlab_id": 100,
            "title_ru": "Майор Мартен Сервас",
            "creator": "Бернар Миньер",
            "release_year": None,
        }
        novel_cand = {
            "source": "fantlab",
            "fantlab_id": 200,
            "title_ru": "Лёд",
            "title_orig": "Glacé",
            "creator": "Бернар Миньер",
            "release_year": 2011,
            "rating_fantlab": 6.72,
        }
        self.assertGreater(
            _score_book_candidate(novel_cand, "Лёд", "Бернар Миньер", 2011),
            _score_book_candidate(series_cand, "Лёд", "Бернар Миньер", 2011),
        )

        # Между двумя огнями — Кристофер Бюльман (2012) находит Between Two Fires — Кристофер Бьюлман (2012)
        fl_client = BooksClient(api_key="dummy")

        def fake_raw_fl(query: str, max_results: int = 10) -> list[dict[str, Any]]:
            if "Бюльман" in query:
                return []
            return [
                {
                    "source": "fantlab",
                    "fantlab_id": 901,
                    "title_ru": "Between Two Fires",
                    "creator": "Кристофер Бьюлман",
                    "release_year": 2012,
                    "rating_fantlab": 5.55,
                },
                {
                    "source": "fantlab",
                    "fantlab_id": 902,
                    "title_ru": "Между двух огней",
                    "creator": "Дайан Швемм",
                    "release_year": 2002,
                },
            ]

        with patch.object(fl_client, "_raw_search_fantlab", side_effect=fake_raw_fl):
            ranked = fl_client.search_candidates("13. Между двумя огнями — Кристофер Бюльман (2012)", limit=3)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["title_ru"], "Between Two Fires")
        self.assertEqual(ranked[0]["creator"], "Кристофер Бьюлман")

    @patch("app.pipeline.books.fetch_goodreads_info", return_value={})
    @patch("app.pipeline.books.fetch_fantlab_info", return_value={"rating_fantlab": 8.1, "summary": "Описание"})
    def test_web_batch_record_original_and_multiline_books(self, _mock_fl: Any, _mock_gr: Any) -> None:
        from app.bot.handlers import ingest_web_item

        conn = get_connection(":memory:")
        apply_migrations(conn)
        settings.tg_chat_id = -1003531389022
        settings.allowed_tg_user_id = 349407845
        settings.topic_books_id = 14

        class MiniBooks:
            def search_candidates(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
                q_low = query.lower()
                if "дерьмо" in q_low:
                    return [{
                        "source": "google_books",
                        "google_books_id": "id_filth",
                        "title_ru": "Дерьмо",
                        "creator": "Ирвин Уэлш",
                        "release_year": 1998,
                    }]
                return [{
                    "source": "google_books",
                    "google_books_id": "id_iliad",
                    "title_ru": "Илион",
                    "creator": "Дэн Симмонс",
                    "release_year": 2003,
                }]

        bc = MiniBooks()
        raw_batch = "1. Дерьмо — Ирвин Уэлш (1998)\n2. Илион — Дэн Симмонс (2003)"
        r_orig = ingest_web_item(conn, raw_batch, topic="books", record_original_only=True, books_client=bc)  # type: ignore[arg-type]
        self.assertEqual(r_orig["status"], "original_recorded")

        r1 = ingest_web_item(conn, "Дерьмо — Ирвин Уэлш (1998)", topic="books", skip_original=True, books_client=bc)  # type: ignore[arg-type]
        r2 = ingest_web_item(conn, "Илион — Дэн Симмонс (2003)", topic="books", skip_original=True, books_client=bc)  # type: ignore[arg-type]
        self.assertEqual(r1["status"], "created")
        self.assertEqual(r2["status"], "created")
        orig_count = conn.execute("SELECT COUNT(*) FROM original_messages").fetchone()[0]
        self.assertEqual(orig_count, 1)

        # Также проверяем многострочный батч через Telegram _handle_message
        tg = DummyTG()
        upd = {
            "update_id": 3005,
            "message": {
                "message_id": 30,
                "message_thread_id": 14,
                "chat": {"id": -1003531389022},
                "from": {"id": 349407845},
                "text": "1. Дерьмо — Ирвин Уэлш (1998)\n2. Илион — Дэн Симмонс (2003)",
            },
        }
        res_batch = handle_update(conn, upd, tg=tg, books_client=bc)  # type: ignore[arg-type]
        self.assertEqual(res_batch["status"], "batch_created")
        self.assertEqual(res_batch["count"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
