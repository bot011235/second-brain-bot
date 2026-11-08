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

        # Удаление из Каталога НЕ удаляет оригинал из архива оригиналов
        item_standalone = repo.create_item(
            conn,
            category="book",
            title_ru="Солярис",
            source_url="https://example.com/solaris",
        )
        orig_standalone = repo.create_original_message(
            conn,
            topic_slug="books",
            raw_text="Солярис Станислав Лем",
            source_url="https://example.com/solaris",
        )
        self.assertTrue(repo.delete_item(conn, item_standalone["id"]))
        self.assertIsNone(repo.get_item(conn, item_standalone["id"]))
        # Оригинал остаётся в сохранности:
        remaining_orig = repo.list_original_messages(conn, tab="books")
        self.assertTrue(any(o["id"] == orig_standalone["id"] for o in remaining_orig))

        # Каскадное удаление из Оригиналов удаляет и привязанный пост из Каталога
        linked_item = repo.create_item(
            conn,
            category="series",
            title_ru="Час дьявола",
            source_url="https://www.threads.com/@morozova_katie/post/DfaRARGCNeh",
            source_type="threads",
            tg_message_id=777,
        )
        del_res = repo.delete_original_message(conn, orig_movies[0]["id"])
        self.assertIsNotNone(del_res)
        assert del_res is not None
        self.assertEqual([it["id"] for it in del_res["deleted_items"]], [linked_item["id"]])
        self.assertIsNone(repo.get_item(conn, linked_item["id"]))
        self.assertEqual(len(repo.list_original_messages(conn, tab="movies")), 0)

    def test_require_tma_auth_and_api_security(self) -> None:
        from fastapi import HTTPException
        from starlette.requests import Request
        from app.config import settings
        from app.main import require_tma_auth

        # Имитируем настройки боевого сервера
        old_token = settings.telegram_bot_token
        old_user_id = settings.allowed_tg_user_id
        old_secret = settings.telegram_webhook_secret
        old_web_key = settings.web_access_key

        settings.telegram_bot_token = "123456:BOT_SECRET"
        settings.allowed_tg_user_id = 349407845
        settings.telegram_webhook_secret = "test_secret_key_123"
        settings.web_access_key = ""

        try:
            # 1. Запрос из браузера без ключа -> 401 Unauthorized
            scope_anon = {
                "type": "http",
                "method": "GET",
                "path": "/api/items",
                "query_string": b"",
                "headers": [],
                "client": ("198.51.100.1", 54321),
            }
            req_anon = Request(scope_anon)
            with self.assertRaises(HTTPException) as cm:
                require_tma_auth(req_anon, authorization=None)
            self.assertEqual(cm.exception.status_code, 401)

            # 2. Запрос из браузера с неверным ключом -> 401 Unauthorized
            scope_wrong = {
                "type": "http",
                "method": "GET",
                "path": "/api/items",
                "query_string": b"",
                "headers": [(b"x-access-key", b"wrong_secret")],
                "client": ("198.51.100.1", 54321),
            }
            req_wrong = Request(scope_wrong)
            with self.assertRaises(HTTPException) as cm:
                require_tma_auth(req_wrong, authorization=None)
            self.assertEqual(cm.exception.status_code, 401)

            # 3. Запрос из браузера с правильным X-Access-Key -> 200 OK (проходит)
            scope_valid_header = {
                "type": "http",
                "method": "GET",
                "path": "/api/items",
                "query_string": b"",
                "headers": [(b"x-access-key", b"test_secret_key_123")],
                "client": ("198.51.100.1", 54321),
            }
            req_valid_header = Request(scope_valid_header)
            user = require_tma_auth(req_valid_header, authorization=None)
            self.assertTrue(user.get("web_key"))

            # 4. Запрос из браузера с правильным query параметром ?key=... -> 200 OK (проходит)
            scope_valid_query = {
                "type": "http",
                "method": "GET",
                "path": "/api/items",
                "query_string": b"key=test_secret_key_123",
                "headers": [],
                "client": ("198.51.100.1", 54321),
            }
            req_valid_query = Request(scope_valid_query)
            user_q = require_tma_auth(req_valid_query, authorization=None)
            self.assertTrue(user_q.get("web_key"))

            # 5. Запрос через TMA с валидной подписью владельца -> 200 OK
            valid_init = _build_signed_init_data(settings.telegram_bot_token, 349407845)
            scope_tma = {
                "type": "http",
                "method": "GET",
                "path": "/api/items",
                "query_string": b"",
                "headers": [],
                "client": ("198.51.100.1", 54321),
            }
            req_tma = Request(scope_tma)
            user_tma = require_tma_auth(req_tma, authorization=f"tma {valid_init}")
            self.assertEqual(user_tma["id"], 349407845)

            # 6. Запрос через TMA с чужим user_id -> 403 Forbidden
            stranger_init = _build_signed_init_data(settings.telegram_bot_token, 999999999)
            with self.assertRaises(HTTPException) as cm:
                require_tma_auth(req_tma, authorization=f"tma {stranger_init}")
            self.assertEqual(cm.exception.status_code, 403)

            # 7. Проверка вебхука: неверный или пустой secret token -> 403 Forbidden
            from app.main import telegram_webhook

            coro1 = telegram_webhook(req_anon, x_telegram_bot_api_secret_token=None)
            with self.assertRaises(HTTPException) as cm_wh1:
                coro1.send(None)
            self.assertEqual(cm_wh1.exception.status_code, 403)

            coro2 = telegram_webhook(req_anon, x_telegram_bot_api_secret_token="wrong_secret")
            with self.assertRaises(HTTPException) as cm_wh2:
                coro2.send(None)
            self.assertEqual(cm_wh2.exception.status_code, 403)

            # 8. Проверка формы входа /api/login для менеджеров паролей:
            from fastapi import Response
            from app.main import LoginPayload, api_login

            settings.web_admin_username = "admin"
            settings.web_admin_password = "test_password_456"

            resp = Response()
            login_res = api_login(LoginPayload(username="admin", password="test_password_456"), resp)
            self.assertEqual(login_res["status"], "ok")
            self.assertEqual(login_res["token"], "test_password_456")
            self.assertIn("sb_access_key", resp.headers.get("set-cookie", ""))

            # Неверный пароль -> 401
            with self.assertRaises(HTTPException) as cm_pwd:
                api_login(LoginPayload(username="admin", password="wrong_password"), resp)
            self.assertEqual(cm_pwd.exception.status_code, 401)

            # Неверный логин -> 401
            with self.assertRaises(HTTPException) as cm_usr:
                api_login(LoginPayload(username="intruder", password="test_password_456"), resp)
            self.assertEqual(cm_usr.exception.status_code, 401)

        finally:
            settings.telegram_bot_token = old_token
            settings.allowed_tg_user_id = old_user_id
            settings.telegram_webhook_secret = old_secret
            settings.web_access_key = old_web_key


if __name__ == "__main__":
    unittest.main(verbosity=2)
