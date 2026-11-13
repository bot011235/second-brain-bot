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

    def set_message_reaction(self, chat_id: int, message_id: int, emoji: str = "👍") -> dict[str, Any]:
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
        item_choice = get_item(conn, item_id)
        assert item_choice is not None
        self.assertEqual(item_choice["processing_status"], "needs_choice")

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

    def test_title_orig_and_parentheses_search(self) -> None:
        from app.pipeline.movies import search_movie_candidates, is_unambiguous_match

        class MockTMDB:
            is_configured = True
            def search_candidates(self, query: str, year: int | None = None, limit: int = 3):
                if query.lower() == "hollow trees":
                    return [{
                        "source": "tmdb",
                        "tmdb_id": 9999,
                        "media_type": "movie",
                        "category": "movie",
                        "title_ru": "Полые деревья",
                        "title_orig": "Hollow Trees",
                        "release_year": 2026,
                    }]
                return []

        mock = MockTMDB()
        # Поиск с скобками 'Полые деревья (Hollow Trees)' находит фильм по оригинальному названию
        cands = search_movie_candidates("Полые деревья (Hollow Trees)", year=2026, tmdb=mock)  # type: ignore[arg-type]
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["title_orig"], "Hollow Trees")
        self.assertTrue(is_unambiguous_match("Полые деревья", 2026, cands, title_orig="Hollow Trees"))

    def test_parse_kinopoisk_share_seo_titles(self) -> None:
        from app.pipeline.movies import parse_title_and_year

        self.assertEqual(
            parse_title_and_year(
                "К востоку от Эдема (сериал, 1 сезон, все серии), 2026 — описание, интересные факты — Кинопоиск\n"
                "https://www.kinopoisk.ru/series/7865896/"
            ),
            ("К востоку от Эдема", 2026),
        )
        self.assertEqual(
            parse_title_and_year(
                "Дом на другой стороне фильм, 2020, дата выхода трейлеры актеры отзывы описание на Кинопоиске\n"
                "https://www.kinopoisk.ru/film/1271405/"
            ),
            ("Дом на другой стороне", 2020),
        )
        self.assertEqual(
            parse_title_and_year("https://www.kinopoisk.ru/series/891601/\nСлучай в Кеттеринге 2016"),
            ("Случай в Кеттеринге", 2016),
        )

    @patch("app.pipeline.movies.resolve_ids_via_wikidata")
    @patch("app.pipeline.movies.fetch_kp_and_imdb_ratings")
    def test_multiline_kinopoisk_link_preserves_kp_id_and_source_url(
        self, mock_ratings: Any, mock_wikidata: Any
    ) -> None:
        conn = get_connection(":memory:")
        apply_migrations(conn)
        settings.tg_chat_id = -1003531389022
        settings.allowed_tg_user_id = 349407845
        settings.topic_movies_id = 3
        settings.telegram_bot_token = "dummy:token"
        tg = DummyTG()

        class ShareTMDB:
            is_configured = True

            def find_by_imdb_id(self, imdb_id: str) -> dict[str, Any] | None:
                if imdb_id == "tt21097264":
                    return {
                        "source": "tmdb",
                        "tmdb_id": 258165,
                        "media_type": "tv",
                        "category": "series",
                        "title_ru": "К востоку от Эдема",
                        "title_orig": "East of Eden",
                        "release_year": 2026,
                    }
                return None

            def get_details(self, media_type: str, tmdb_id: int) -> dict[str, Any]:
                if tmdb_id == 258165:
                    return {
                        "tmdb_id": 258165,
                        "media_type": "tv",
                        "category": "series",
                        "title_ru": "К востоку от Эдема",
                        "title_orig": "East of Eden",
                        "release_year": 2026,
                        "summary": "Экранизация романа Стейнбека.",
                        "poster_url": "https://image.tmdb.org/t/p/w500/eden.jpg",
                        "genres": ["драма"],
                        "imdb_id": "tt21097264",
                    }
                return {
                    "tmdb_id": 249597,
                    "media_type": "tv",
                    "category": "series",
                    "title_ru": "Харри Холе",
                    "title_orig": "Harry Hole",
                    "release_year": 2026,
                    "summary": "Криминальный детектив.",
                    "poster_url": "https://image.tmdb.org/t/p/w500/hole.jpg",
                    "genres": ["криминал", "триллер"],
                }

            def search_candidates(self, query: str, year: int | None = None, limit: int = 3) -> list[dict[str, Any]]:
                if query == "Детектив Холе" and year == 2026:
                    return [
                        {
                            "source": "tmdb",
                            "tmdb_id": 249597,
                            "media_type": "tv",
                            "category": "series",
                            "title_ru": "Харри Холе",
                            "title_orig": "Harry Hole",
                            "release_year": 2026,
                        }
                    ]
                return []

        tmdb = ShareTMDB()

        # 1. Ссылка на 2-й строке резолвится через Wikidata kp_id -> imdb_id -> TMDB и сохраняет source_url
        mock_wikidata.return_value = {"imdb_id": "tt21097264", "kp_id": 7865896}
        mock_ratings.return_value = {"rating_kp": None, "rating_imdb": None}
        upd_eden = {
            "update_id": 3001,
            "message": {
                "message_id": 101,
                "message_thread_id": 3,
                "chat": {"id": -1003531389022},
                "from": {"id": 349407845},
                "text": (
                    "К востоку от Эдема (сериал, 1 сезон, все серии), 2026 — описание, интересные факты — Кинопоиск\n"
                    "https://www.kinopoisk.ru/series/7865896/"
                ),
            },
        }
        res_eden = handle_update(conn, upd_eden, tg=tg, tmdb=tmdb)  # type: ignore[arg-type]
        self.assertEqual(res_eden["status"], "created")
        item_eden = get_item(conn, res_eden["item_id"])
        assert item_eden is not None
        self.assertEqual(item_eden["kp_id"], 7865896)
        self.assertEqual(item_eden["imdb_id"], "tt21097264")
        self.assertEqual(item_eden["sources"][0]["source_url"], "https://www.kinopoisk.ru/series/7865896/")

        # 2. Если в Wikidata пусто, очистка SEO-хвоста находит в TMDB и сохраняет kp_id со 2-й строки
        mock_wikidata.return_value = {}
        upd_hole = {
            "update_id": 3002,
            "message": {
                "message_id": 102,
                "message_thread_id": 3,
                "chat": {"id": -1003531389022},
                "from": {"id": 349407845},
                "text": (
                    "Детектив Холе (сериал, 1 сезон, все серии), 2026 — описание, интересные факты — Кинопоиск\n"
                    "https://www.kinopoisk.ru/series/6399289/"
                ),
            },
        }
        res_hole = handle_update(conn, upd_hole, tg=tg, tmdb=tmdb)  # type: ignore[arg-type]
        self.assertEqual(res_hole["status"], "created")
        item_hole = get_item(conn, res_hole["item_id"])
        assert item_hole is not None
        self.assertEqual(item_hole["kp_id"], 6399289)
        self.assertEqual(item_hole["title_ru"], "Харри Холе")
        self.assertEqual(item_hole["sources"][0]["source_url"], "https://www.kinopoisk.ru/series/6399289/")


if __name__ == "__main__":
    unittest.main(verbosity=2)
