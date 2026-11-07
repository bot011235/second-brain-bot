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


class FakeTMDBClient:
    is_configured = True

    def search_candidates(self, query: str, year: int | None = None, limit: int = 3) -> list[dict[str, Any]]:
        if "разделение" in query.lower():
            return [
                {
                    "source": "tmdb",
                    "tmdb_id": 95396,
                    "media_type": "tv",
                    "category": "series",
                    "title_ru": "Разделение",
                    "title_orig": "Severance",
                    "release_year": 2022,
                    "summary": "Сотрудникам компании Lumon разделяют рабочие и личные воспоминания.",
                    "poster_url": "https://image.tmdb.org/t/p/w500/severance.jpg",
                    "rating_tmdb": 8.4,
                },
                {
                    "source": "tmdb",
                    "tmdb_id": 12345,
                    "media_type": "movie",
                    "category": "movie",
                    "title_ru": "Разделение",
                    "title_orig": "The Divide",
                    "release_year": 2011,
                    "summary": "Постапокалиптический триллер в бункере.",
                    "poster_url": None,
                    "rating_tmdb": 5.8,
                },
            ]
        return []

    def get_details(self, media_type: str, tmdb_id: int) -> dict[str, Any]:
        return {
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "category": "series" if media_type == "tv" else "movie",
            "title_ru": "Разделение",
            "title_orig": "Severance",
            "release_year": 2022,
            "summary": "Сотрудникам компании Lumon разделяют рабочие и личные воспоминания.",
            "poster_url": "https://image.tmdb.org/t/p/w500/severance.jpg",
            "genres": ["драма", "фантастика", "триллер"],
            "creator": "Дэн Эриксон",
            "imdb_id": "tt11280740",
            "wikidata_id": "Q85800706",
            "rating_tmdb": 8.4,
        }


class DummyTG:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.edited: list[dict[str, Any]] = []
        self.deleted: list[int] = []

    def send_message(self, chat_id: int, text: str, **kwargs: Any) -> dict[str, Any]:
        self.sent.append({"chat_id": chat_id, "text": text, **kwargs})
        return {"ok": True, "result": {"message_id": 500 + len(self.sent)}}

    def edit_message_text(self, chat_id: int, message_id: int, text: str, **kwargs: Any) -> dict[str, Any]:
        self.edited.append({"chat_id": chat_id, "message_id": message_id, "text": text, **kwargs})
        return {"ok": True}

    def delete_message(self, chat_id: int, message_id: int) -> dict[str, Any]:
        self.deleted.append(message_id)
        return {"ok": True}

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> dict[str, Any]:
        return {"ok": True}


class TestStage2Movies(unittest.TestCase):
    @patch("app.pipeline.movies.resolve_ids_via_wikidata")
    @patch("app.pipeline.movies.fetch_kp_and_imdb_ratings")
    def test_disambiguation_and_dedup(self, mock_ratings: Any, mock_wikidata: Any) -> None:
        mock_wikidata.return_value = {
            "imdb_id": "tt11280740",
            "kp_id": 1343318,
            "url_rt": "https://www.rottentomatoes.com/tv/severance",
        }
        mock_ratings.return_value = {"rating_kp": 8.2, "rating_imdb": 8.7}

        conn = get_connection(":memory:")
        apply_migrations(conn)

        settings.tg_chat_id = -1003531389022
        settings.allowed_tg_user_id = 349407845
        settings.topic_movies_id = 3
        settings.telegram_bot_token = "dummy:token"

        tg = DummyTG()
        tmdb = FakeTMDBClient()

        # 1. Неоднозначный запрос 'Разделение' -> карточка выбора из 2 кандидатов
        upd1 = {
            "update_id": 2001,
            "message": {
                "message_id": 10,
                "message_thread_id": 3,
                "chat": {"id": -1003531389022},
                "from": {"id": 349407845},
                "text": "Разделение",
            },
        }
        res1 = handle_update(conn, upd1, tg=tg, tmdb=tmdb)  # type: ignore[arg-type]
        self.assertEqual(res1["status"], "needs_choice")
        item_id = res1["item_id"]
        self.assertIn("найдено несколько вариантов", tg.sent[-1]["text"])

        # 2. Пользователь нажимает кнопку 1-го кандидата (Severance 2022)
        cb = {
            "update_id": 2002,
            "callback_query": {
                "id": "cb_pick",
                "from": {"id": 349407845},
                "message": {"message_id": 501, "chat": {"id": -1003531389022}},
                "data": f"pick:{item_id}:0",
            },
        }
        res2 = handle_update(conn, cb, tg=tg, tmdb=tmdb)  # type: ignore[arg-type]
        self.assertEqual(res2["status"], "enriched")

        item = get_item(conn, item_id)
        assert item is not None
        self.assertEqual(item["category"], "series")
        self.assertEqual(item["imdb_id"], "tt11280740")
        self.assertEqual(item["kp_id"], 1343318)
        self.assertEqual(item["rating_imdb"], 8.7)
        self.assertEqual(item["rating_kp"], 8.2)
        self.assertIn("драма", item["genres"])
        self.assertIn("IMDb <b>8.7</b>", tg.edited[-1]["text"])
        self.assertIn("КП <b>8.2</b>", tg.edited[-1]["text"])

        # 3. Повторная отправка с точным годом 'Разделение 2022' -> срабатывает дедупликация!
        upd3 = {
            "update_id": 2003,
            "message": {
                "message_id": 11,
                "message_thread_id": 3,
                "chat": {"id": -1003531389022},
                "from": {"id": 349407845},
                "text": "Разделение 2022",
            },
        }
        res3 = handle_update(conn, upd3, tg=tg, tmdb=tmdb)  # type: ignore[arg-type]
        self.assertEqual(res3["status"], "duplicate_item")
        self.assertEqual(res3["item_id"], item_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
