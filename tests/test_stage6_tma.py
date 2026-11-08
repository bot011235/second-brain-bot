from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import repo
from app.db.client import get_connection
from app.db.migrate import apply_migrations
from app.utils.initdata import verify_telegram_init_data


def _build_signed_init_data(bot_token: str, user_id: int) -> str:
    params = {
        "auth_date": str(int(time.time())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps({"id": user_id, "first_name": "Vlad"}),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    sig = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    params["hash"] = sig
    return urlencode(params)


class TestStage6TMA(unittest.TestCase):
    def test_hmac_init_data_verification(self) -> None:
        token = "123456:ABCDEF_secret"
        init_data = _build_signed_init_data(token, 349407845)

        user = verify_telegram_init_data(init_data, bot_token=token, allowed_user_id=349407845)
        self.assertIsNotNone(user)
        assert user is not None
        self.assertEqual(user["id"], 349407845)

        # Чужой user_id отклоняется
        self.assertIsNone(verify_telegram_init_data(init_data, bot_token=token, allowed_user_id=999))
        # Поддельный токен отклоняется
        self.assertIsNone(verify_telegram_init_data(init_data, bot_token="wrong", allowed_user_id=349407845))

    def test_catalog_filtering_and_sorting(self) -> None:
        conn = get_connection(":memory:")
        apply_migrations(conn)

        m1 = repo.create_item(
            conn,
            category="movie",
            title_ru="Дюна",
            rating_imdb=8.0,
            rating_kp=7.7,
            rating_rt=83,
            genres=["фантастика", "драма"],
        )
        m2 = repo.create_item(
            conn,
            category="series",
            title_ru="Разделение",
            rating_imdb=8.7,
            rating_kp=8.2,
            rating_rt=97,
            genres=["триллер", "фантастика"],
        )
        b1 = repo.create_item(
            conn,
            category="book",
            title_ru="Гиперион",
            rating_imdb=4.28,
            rating_kp=8.56,
            genres=["фантастика"],
        )

        # Сортировка фильмов по RT ↓
        movies_rt = repo.list_items_catalog(conn, tab="movies", sort="rt")
        self.assertEqual([i["id"] for i in movies_rt], [m2["id"], m1["id"]])

        # Фильтр по жанру 'триллер'
        thrillers = repo.list_items_catalog(conn, tag="триллер")
        self.assertEqual([i["id"] for i in thrillers], [m2["id"]])

        # Вкладка книг
        books = repo.list_items_catalog(conn, tab="books")
        self.assertEqual([i["id"] for i in books], [b1["id"]])

        # Архив оригиналов: фильтрация по категории чата и простой поиск
        repo.create_original_message(
            conn,
            topic_slug="movies",
            raw_text="https://www.threads.com/share/_un9gYcFq",
            source_url="https://www.threads.com/@morozova_katie/post/DfaRARGCNeh",
            source_type="threads",
            author="@morozova_katie",
            extracted_text="Хто любить Dark, Ззовні, дуже рекомендую Час Дияволa",
        )
        repo.create_original_message(
            conn,
            topic_slug="books",
            raw_text="Гиперион Дэн Симмонс",
            source_type="manual",
        )

        orig_movies = repo.list_original_messages(conn, tab="movies")
        self.assertEqual(len(orig_movies), 1)
        self.assertEqual(orig_movies[0]["author"], "@morozova_katie")

        orig_search = repo.list_original_messages(conn, q="Диявол")
        self.assertEqual(len(orig_search), 1)
        self.assertEqual(orig_search[0]["topic_slug"], "movies")


if __name__ == "__main__":
    unittest.main(verbosity=2)
