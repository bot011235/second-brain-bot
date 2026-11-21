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
        old_admin_user = settings.web_admin_username
        old_admin_pwd = settings.web_admin_password

        settings.telegram_bot_token = "123456:BOT_SECRET"
        settings.allowed_tg_user_id = 349407845
        settings.telegram_webhook_secret = "test_secret_key_123"
        settings.web_access_key = ""
        settings.web_admin_username = "admin"
        settings.web_admin_password = ""

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

            # Старый ключ вебхука отклоняется, если задан web_admin_password -> 401
            with self.assertRaises(HTTPException) as cm_old:
                api_login(LoginPayload(username="admin", password="test_secret_key_123"), resp)
            self.assertEqual(cm_old.exception.status_code, 401)

        finally:
            settings.telegram_bot_token = old_token
            settings.allowed_tg_user_id = old_user_id
            settings.telegram_webhook_secret = old_secret
            settings.web_access_key = old_web_key
            settings.web_admin_username = old_admin_user
            settings.web_admin_password = old_admin_pwd

    def test_update_fields_and_web_ingest_endpoints(self) -> None:
        from unittest.mock import patch
        import app.main as main_mod
        from app.config import settings
        from app.bot.handlers import ingest_web_item

        conn = get_connection(":memory:")
        apply_migrations(conn)

        class _NoCloseConn:
            def __init__(self, inner):
                self._inner = inner

            def execute(self, *args, **kwargs):
                return self._inner.execute(*args, **kwargs)

            def commit(self):
                return self._inner.commit()

            def close(self):
                return None

        old_llm_ideas = settings.llm_for_ideas
        settings.llm_for_ideas = False
        try:
            # 1. Расширенное обновление полей, заметок и тегов + get_item c extracted_text
            created = repo.create_item(
                conn,
                category="article",
                title_ru="Исходный заголовок",
                canonical_url="https://example.com/post-1",
                summary="Короткое описание",
                tags=["статья"],
            )
            repo.create_original_message(
                conn,
                topic_slug="article",
                raw_text="https://example.com/post-1",
                source_url="https://example.com/post-1",
                source_type="web",
                extracted_text="Полный текст статьи из оригинала для режима чтения.",
            )

            updated = repo.update_item_fields(
                conn,
                created["id"],
                status="planned",
                user_rating=9,
                title_ru="Обновлённый заголовок",
                summary="Новое описание для теста",
                user_note="Прочитать в воскресенье утром",
                tags=["лонгрид", "ui"],
            )
            self.assertIsNotNone(updated)
            assert updated is not None
            self.assertEqual(updated["title_ru"], "Обновлённый заголовок")
            self.assertEqual(updated["status"], "planned")
            self.assertEqual(updated["user_rating"], 9)
            self.assertEqual(updated["tags"], ["ui", "лонгрид"])
            self.assertEqual(updated["extracted_text"], "Полный текст статьи из оригинала для режима чтения.")
            meta_obj = json.loads(updated["meta"])
            self.assertEqual(meta_obj.get("user_note"), "Прочитать в воскресенье утром")

            # Проверяем пересборку FTS5-индекса после смены заголовка и тега
            fts_hits = repo.list_items_catalog(conn, q="Обновлённый")
            self.assertEqual([it["id"] for it in fts_hits], [created["id"]])

            # 2. Прямое добавление идеи с веб-витрины через ingest_web_item + POST /api/items и PATCH /api/items/{id}
            res_idea = ingest_web_item(conn, "Сделать дашборд #ui #продуктивность", topic="ideas")
            self.assertEqual(res_idea["status"], "created")
            self.assertTrue(res_idea.get("item_id"))

            wrapped = _NoCloseConn(conn)
            with patch.object(main_mod, "get_connection", return_value=wrapped):
                post_data = main_mod.api_create_item(
                    main_mod.CreateItemPayload(text="Быстрая заметка #тест", topic="ideas"),
                    _user={"id": 349407845},
                )
                self.assertEqual(post_data["status"], "created")
                new_id = post_data["item"]["id"]

                patch_data = main_mod.api_patch_item(
                    new_id,
                    main_mod.PatchItemPayload(user_note="Проверить вечером", tags=["тест", "заметка"]),
                    _user={"id": 349407845},
                )
                self.assertEqual(patch_data["tags"], ["заметка", "тест"])
                self.assertEqual(json.loads(patch_data["meta"])["user_note"], "Проверить вечером")
        finally:
            settings.llm_for_ideas = old_llm_ideas

    def test_stage3_fts_search_multitags_and_smart_views(self) -> None:
        from unittest.mock import patch
        import app.main as main_mod

        conn = get_connection(":memory:")
        apply_migrations(conn)

        class _NoCloseConn:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def close(self):
                return None

        # 1. Идеальный фильм в планах с высоким рейтингом (top_planned) + мульти-тегами + заметкой (noted)
        it_top_movie = repo.create_item(
            conn,
            category="movie",
            title_ru="Дюна: Часть вторая",
            title_orig="Dune: Part Two",
            status="planned",
            rating_imdb=8.6,
            rating_kp=8.3,
            tags=["sci-fi", "classic", "imax"],
        )
        repo.update_item_fields(
            conn,
            it_top_movie["id"],
            user_note="Пересмотреть на большом экране с кинематографичным звуком",
        )

        # 2. Фильм из inbox с высоким рейтингом (top_planned) и частичным пересечением тегов
        it_inbox_movie = repo.create_item(
            conn,
            category="movie",
            title_ru="Прибытие",
            title_orig="Arrival",
            status="inbox",
            rating_imdb=7.9,
            tags=["sci-fi"],
        )

        # 3. Завершённая книга с личной оценкой >= 8 (favorites)
        it_fav_book = repo.create_item(
            conn,
            category="book",
            title_ru="Гиперион",
            creator="Дэн Симмонс",
            status="done",
            rating_imdb=4.3,
            tags=["sci-fi", "classic"],
        )
        repo.update_item_fields(conn, it_fav_book["id"], user_rating=9)

        # 4. Завершённая запись без личной оценки (unrated_done)
        it_unrated_done = repo.create_item(
            conn,
            category="article",
            title_ru="Эффективные паттерны локального поиска",
            status="done",
            tags=["dev"],
        )

        # 5. Запись с ошибкой обогащения (attention)
        it_attention = repo.create_item(
            conn,
            category="movie",
            title_ru="Неизвестный релиз",
            status="inbox",
            processing_status="failed",
        )

        try:
            # FTS5 префиксный поиск по кириллице и user_note
            note_hits = repo.list_items_catalog(conn, q="кинематограф")
            self.assertEqual([x["id"] for x in note_hits], [it_top_movie["id"]])

            # Поиск через #тег
            hash_hits = repo.list_items_catalog(conn, q="#imax")
            self.assertEqual([x["id"] for x in hash_hits], [it_top_movie["id"]])

            # Мульти-теги с логикой AND (через запятую)
            multi_tag_hits = repo.list_items_catalog(conn, tag="sci-fi,classic")
            self.assertEqual(
                {x["id"] for x in multi_tag_hits},
                {it_top_movie["id"], it_fav_book["id"]},
            )
            self.assertNotIn(it_inbox_movie["id"], [x["id"] for x in multi_tag_hits])

            # 5 умных представлений (Smart Views)
            self.assertEqual(
                {x["id"] for x in repo.list_items_catalog(conn, smart="top_planned")},
                {it_top_movie["id"], it_inbox_movie["id"]},
            )
            self.assertEqual(
                [x["id"] for x in repo.list_items_catalog(conn, smart="favorites")],
                [it_fav_book["id"]],
            )
            self.assertEqual(
                [x["id"] for x in repo.list_items_catalog(conn, smart="noted")],
                [it_top_movie["id"]],
            )
            self.assertEqual(
                [x["id"] for x in repo.list_items_catalog(conn, smart="unrated_done")],
                [it_unrated_done["id"]],
            )
            self.assertEqual(
                [x["id"] for x in repo.list_items_catalog(conn, smart="attention")],
                [it_attention["id"]],
            )

            # Прямой вызов FastAPI-эндпоинта /api/items c smart="favorites"
            wrapped = _NoCloseConn(conn)
            with patch.object(main_mod, "get_connection", return_value=wrapped):
                api_res = main_mod.api_list_items(
                    tab=None,
                    status=None,
                    tag=None,
                    q=None,
                    sort="created",
                    limit=200,
                    offset=0,
                    smart="favorites",
                    _user={"id": 349407845},
                )
            self.assertEqual(api_res["count"], 1)
            self.assertEqual(api_res["total"], 1)
            self.assertFalse(api_res["has_more"])
            self.assertEqual([x["id"] for x in api_res["items"]], [it_fav_book["id"]])
        finally:
            conn.close()

    def test_stage5_pagination_sorts_and_status_counts(self) -> None:
        from unittest.mock import patch
        import app.main as main_mod

        conn = get_connection(":memory:")
        apply_migrations(conn)

        class _NoCloseConn:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def close(self):
                return None

        it_a = repo.create_item(
            conn,
            category="movie",
            title_ru="Альфа",
            release_year=2020,
            status="planned",
        )
        it_b = repo.create_item(
            conn,
            category="movie",
            title_ru="Бета",
            release_year=2025,
            status="done",
        )
        it_g = repo.create_item(
            conn,
            category="book",
            title_ru="Гамма",
            release_year=2022,
            status="inbox",
        )
        conn.execute(
            "UPDATE items SET updated_at = datetime('now', '+1 day') WHERE id = ?",
            (it_a["id"],),
        )
        conn.commit()

        try:
            # 1. Сортировки year, title, updated
            by_year = repo.list_items_catalog(conn, sort="year")
            self.assertEqual([x["id"] for x in by_year], [it_b["id"], it_g["id"], it_a["id"]])

            by_title = repo.list_items_catalog(conn, sort="title")
            self.assertEqual([x["id"] for x in by_title], [it_a["id"], it_b["id"], it_g["id"]])

            by_updated = repo.list_items_catalog(conn, sort="updated")
            self.assertEqual(by_updated[0]["id"], it_a["id"])

            # 2. Пагинация limit/offset и реальные счётчики статусов
            self.assertEqual(repo.count_items_catalog(conn), 3)
            self.assertEqual(
                repo.get_status_counts_by_tab(conn),
                {"all": 3, "inbox": 1, "planned": 1, "in_progress": 0, "done": 1, "dropped": 0},
            )

            wrapped = _NoCloseConn(conn)
            with patch.object(main_mod, "get_connection", return_value=wrapped):
                page1 = main_mod.api_list_items(
                    tab=None,
                    status=None,
                    tag=None,
                    q=None,
                    sort="title",
                    limit=2,
                    offset=0,
                    smart=None,
                    _user={"id": 349407845},
                )
                page2 = main_mod.api_list_items(
                    tab=None,
                    status=None,
                    tag=None,
                    q=None,
                    sort="title",
                    limit=2,
                    offset=2,
                    smart=None,
                    _user={"id": 349407845},
                )

            self.assertEqual([x["id"] for x in page1["items"]], [it_a["id"], it_b["id"]])
            self.assertEqual(page1["total"], 3)
            self.assertTrue(page1["has_more"])
            self.assertEqual(page1["status_counts"]["inbox"], 1)

            self.assertEqual([x["id"] for x in page2["items"]], [it_g["id"]])
            self.assertEqual(page2["total"], 3)
            self.assertFalse(page2["has_more"])
            self.assertNotIn("status_counts", page2)
        finally:
            conn.close()

    def test_stage4_bulk_actions_and_stats(self) -> None:
        from unittest.mock import patch
        from fastapi import HTTPException
        import app.main as main_mod

        conn = get_connection(":memory:")
        apply_migrations(conn)

        class _NoCloseConn:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def close(self):
                return None

        it_movie = repo.create_item(
            conn,
            category="movie",
            title_ru="Бегущий по лезвию",
            status="planned",
            tags=["cyberpunk", "sci-fi"],
        )
        it_book = repo.create_item(
            conn,
            category="book",
            title_ru="Солярис",
            creator="Станислав Лем",
            status="inbox",
            tags=["sci-fi"],
        )
        it_article = repo.create_item(
            conn,
            category="article",
            title_ru="Заметка для удаления",
            status="inbox",
            tags=["temp"],
        )
        repo.update_item_fields(
            conn,
            it_movie["id"],
            user_rating=9,
            user_note="Лучший нео-нуар",
        )
        repo.update_item_fields(conn, it_book["id"], user_rating=7)

        try:
            # 1. Bulk смена статуса и добавление тега с пересборкой FTS5
            bulk_st = repo.bulk_update_items(conn, [it_movie["id"], it_book["id"]], status="done")
            self.assertEqual(bulk_st["action"], "status")
            self.assertEqual(bulk_st["affected"], 2)

            bulk_tag = repo.bulk_update_items(conn, [it_movie["id"], it_book["id"]], add_tag="#must-watch")
            self.assertEqual(bulk_tag["action"], "add_tag")
            self.assertEqual(bulk_tag["tag"], "must-watch")
            self.assertEqual(bulk_tag["affected"], 2)

            tag_hits = repo.list_items_catalog(conn, q="#must-watch")
            self.assertEqual({x["id"] for x in tag_hits}, {it_movie["id"], it_book["id"]})

            with self.assertRaises(ValueError):
                repo.bulk_update_items(conn, [it_movie["id"]], status="unknown_status")

            # 2. Агрегированная статистика и дневник
            stats = repo.get_catalog_stats(conn)
            self.assertEqual(stats["summary"]["total"], 3)
            self.assertEqual(stats["summary"]["done"], 2)
            self.assertEqual(stats["summary"]["inbox"], 1)
            self.assertEqual(stats["summary"]["rated_count"], 2)
            self.assertEqual(stats["summary"]["avg_user_rating"], 8.0)
            self.assertEqual(stats["summary"]["noted_count"], 1)

            self.assertEqual([c["tab"] for c in stats["by_category"]], ["movies", "books", "video", "article", "ideas"])
            self.assertEqual(len(stats["ratings_distribution"]), 10)
            r_map = {r["rating"]: r["count"] for r in stats["ratings_distribution"]}
            self.assertEqual(r_map[9], 1)
            self.assertEqual(r_map[7], 1)
            self.assertTrue(any(t["tag"] == "sci-fi" and t["count"] == 2 for t in stats["top_tags"]))
            self.assertEqual({d["id"] for d in stats["diary"]}, {it_movie["id"], it_book["id"]})

            stats_empty_yr = repo.get_catalog_stats(conn, year=2099)
            self.assertEqual(stats_empty_yr["summary"]["total"], 0)
            self.assertEqual(len(stats_empty_yr["monthly"]), 12)

            # 3. Прямые вызовы FastAPI-эндпоинтов /api/stats и /api/items/bulk
            wrapped = _NoCloseConn(conn)
            with patch.object(main_mod, "get_connection", return_value=wrapped):
                api_stats = main_mod.api_get_stats(year=None, _user={"id": 349407845})
                self.assertEqual(api_stats["summary"]["done"], 2)

                api_del = main_mod.api_bulk_items(
                    main_mod.BulkItemsPayload(item_ids=[it_article["id"]], delete=True),
                    _user={"id": 349407845},
                )
                self.assertEqual(api_del["action"], "delete")
                self.assertEqual(api_del["affected"], 1)

                with self.assertRaises(HTTPException) as ctx:
                    main_mod.api_bulk_items(
                        main_mod.BulkItemsPayload(item_ids=[it_movie["id"]], status="invalid"),
                        _user={"id": 349407845},
                    )
                self.assertEqual(ctx.exception.status_code, 400)

            self.assertIsNone(repo.get_item(conn, it_article["id"]))
        finally:
            conn.close()

    def test_stage6_highlights_progress_and_reenrich(self) -> None:
        from unittest.mock import patch
        from fastapi import HTTPException
        import app.main as main_mod
        from app.bot import handlers as handlers_mod
        from app.pipeline import movies as movies_pipeline

        class _NoCloseConn:
            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def close(self) -> None:
                pass

        class _DummyLLM:
            is_configured = False

        conn = get_connection(":memory:")
        apply_migrations(conn)
        try:
            it_art = repo.create_item(
                conn,
                category="article",
                title_ru="Длинная статья о нейробиологии",
                canonical_url="https://example.com/neuro-article",
                source_url="https://example.com/neuro-article",
                source_type="web",
                processing_status="needs_input",
                tags=["наука"],
            )
            it_series = repo.create_item(
                conn,
                category="series",
                title_ru="Разделение",
                release_year=2022,
                meta={"seasons_count": 2},
            )
            it_book = repo.create_item(
                conn,
                category="book",
                title_ru="Дюна",
                creator="Фрэнк Герберт",
                meta={"page_count": 600},
            )
            it_existing_movie = repo.create_item(
                conn,
                category="movie",
                title_ru="Прибытие (дубль ID)",
                release_year=2016,
                imdb_id="tt2543164",
                kp_id=718811,
            )
            it_movie = repo.create_item(
                conn,
                category="movie",
                title_ru="Прибытие",
                release_year=2016,
                status="in_progress",
                processing_status="needs_input",
                tags=["любимое"],
                meta={"user_note": "Смотреть в оригинале"},
            )
            repo.update_item_fields(conn, it_movie["id"], user_rating=9)

            wrapped = _NoCloseConn(conn)
            with patch.object(main_mod, "get_connection", return_value=wrapped):
                # 1. Сохранение цитат/хайлайтов + индексация в FTS5 и умном списке smart="noted"
                patched_art = main_mod.api_patch_item(
                    it_art["id"],
                    main_mod.PatchItemPayload(
                        highlights=[
                            {"id": "hl-1", "text": "Синаптическая пластичность усиливается при глубоком сне", "note": "Важный тезис"},
                        ],
                        progress={"kind": "read", "scroll_pct": 65},
                    ),
                    _user={"id": 349407845},
                )
                art_meta = json.loads(patched_art["meta"])
                self.assertEqual(len(art_meta["highlights"]), 1)
                self.assertEqual(art_meta["highlights"][0]["note"], "Важный тезис")
                self.assertEqual(art_meta["progress"]["kind"], "read")
                self.assertEqual(art_meta["progress"]["scroll_pct"], 65)

                fts_hits = repo.list_items_catalog(conn, q="Синаптическая")
                self.assertEqual([x["id"] for x in fts_hits], [it_art["id"]])

                noted_hits = repo.list_items_catalog(conn, smart="noted")
                self.assertIn(it_art["id"], {x["id"] for x in noted_hits})

                # Очистка хайлайтов удаляет их из meta и FTS5
                cleared_art = main_mod.api_patch_item(
                    it_art["id"],
                    main_mod.PatchItemPayload(highlights=[]),
                    _user={"id": 349407845},
                )
                self.assertNotIn("highlights", json.loads(cleared_art["meta"]))
                self.assertEqual(repo.list_items_catalog(conn, q="Синаптическая"), [])

                # 2. Прогресс сериалов и книг + валидация ошибок
                patched_ser = main_mod.api_patch_item(
                    it_series["id"],
                    main_mod.PatchItemPayload(progress={"kind": "series", "season": 2, "episode": 5, "total_seasons": 2}),
                    _user={"id": 349407845},
                )
                ser_prog = json.loads(patched_ser["meta"])["progress"]
                self.assertEqual((ser_prog["season"], ser_prog["episode"]), (2, 5))

                patched_book = main_mod.api_patch_item(
                    it_book["id"],
                    main_mod.PatchItemPayload(progress={"kind": "book", "page": 150, "total_pages": 600}),
                    _user={"id": 349407845},
                )
                book_prog = json.loads(patched_book["meta"])["progress"]
                self.assertEqual((book_prog["page"], book_prog["total_pages"], book_prog["percent"]), (150, 600, 25))

                cleared_book = main_mod.api_patch_item(
                    it_book["id"],
                    main_mod.PatchItemPayload(progress={}),
                    _user={"id": 349407845},
                )
                self.assertNotIn("progress", json.loads(cleared_book["meta"]))

                with self.assertRaises(HTTPException) as ctx:
                    main_mod.api_patch_item(
                        it_book["id"],
                        main_mod.PatchItemPayload(progress={"kind": "unknown_kind"}),
                        _user={"id": 349407845},
                    )
                self.assertEqual(ctx.exception.status_code, 400)

                # 3. Переобогащение фильма с сохранением пользовательских данных и защитой от UNIQUE-коллизий
                main_mod.api_patch_item(
                    it_movie["id"],
                    main_mod.PatchItemPayload(
                        highlights=[{"id": "hl-m", "text": "Любимая цитата из фильма"}],
                    ),
                    _user={"id": 349407845},
                )
                fake_enriched_movie = {
                    "category": "movie",
                    "title_ru": "Прибытие",
                    "title_orig": "Arrival",
                    "release_year": 2016,
                    "creator": "Дени Вильнёв",
                    "summary": "Лингвист пытается расшифровать язык пришельцев.",
                    "poster_url": "https://image.tmdb.org/t/p/w500/arrival.jpg",
                    "imdb_id": it_existing_movie["imdb_id"],  # коллизия UNIQUE с другой записью!
                    "kp_id": it_existing_movie["kp_id"],      # коллизия UNIQUE с другой записью!
                    "rating_imdb": 7.9,
                    "rating_kp": 7.6,
                    "rating_rt": 94,
                    "url_rt": "https://www.rottentomatoes.com/m/arrival_2016",
                    "genres": ["фантастика", "драма"],
                    "meta": {"tmdb_id": 329865, "rating_tmdb": 7.6},
                }
                with patch.object(movies_pipeline, "search_movie_candidates", return_value=[{"tmdb_id": 329865}]), patch.object(
                    movies_pipeline, "enrich_candidate", return_value=fake_enriched_movie
                ):
                    re_res = main_mod.api_reenrich_item(it_movie["id"], _user={"id": 349407845})
                    self.assertEqual(re_res["status"], "updated")
                    self.assertIn("poster_url", re_res["updated_fields"])
                    self.assertIn("rating_imdb", re_res["updated_fields"])
                    re_item = re_res["item"]
                    self.assertEqual(re_item["processing_status"], "ok")
                    self.assertEqual(re_item["status"], "in_progress")
                    self.assertEqual(re_item["user_rating"], 9)
                    self.assertIn("любимое", re_item["tags"])
                    re_meta = json.loads(re_item["meta"])
                    self.assertEqual(re_meta["user_note"], "Смотреть в оригинале")
                    self.assertEqual(re_meta["highlights"][0]["text"], "Любимая цитата из фильма")
                    self.assertEqual(re_meta["tmdb_id"], 329865)

                # 4. Переобогащение статьи обновляет extracted_text, постер и статус
                fake_scraped = {
                    "ok": True,
                    "canonical_url": "https://example.com/neuro-article",
                    "title": "Длинная статья о нейробиологии",
                    "text": "Полный текст статьи из трёх абзацев для чтения в Zen Reader.",
                    "author": "Д-р Смит",
                    "poster_url": "https://example.com/neuro.jpg",
                }
                art_re = handlers_mod.reenrich_item(
                    conn,
                    it_art["id"],
                    llm_client=_DummyLLM(),
                    scrape_fn=lambda _u: fake_scraped,
                )
                self.assertEqual(art_re["status"], "updated")
                self.assertEqual(art_re["item"]["processing_status"], "ok")
                self.assertEqual(art_re["item"]["poster_url"], "https://example.com/neuro.jpg")
                self.assertEqual(
                    art_re["item"]["extracted_text"],
                    "Полный текст статьи из трёх абзацев для чтения в Zen Reader.",
                )
                self.assertEqual(json.loads(art_re["item"]["meta"])["progress"]["scroll_pct"], 65)

                with self.assertRaises(HTTPException) as ctx404:
                    main_mod.api_reenrich_item(999999, _user={"id": 349407845})
                self.assertEqual(ctx404.exception.status_code, 404)
        finally:
            conn.close()

    def test_tma_static_ui_contract(self) -> None:
        import mimetypes
        import re
        import app.main as main_mod

        tma_dir = Path(__file__).resolve().parent.parent / "app" / "tma"
        self.assertEqual(main_mod.TMA_DIR.resolve(), tma_dir.resolve())
        html = (tma_dir / "index.html").read_text(encoding="utf-8")
        css = (tma_dir / "styles.css").read_text(encoding="utf-8")
        js = (tma_dir / "app.js").read_text(encoding="utf-8")

        # 1. Версия ассетов v33, PWA-манифест + иконки + Service Worker, Literata
        self.assertIn("./styles.css?v=33", html)
        self.assertIn("./app.js?v=33", html)
        self.assertIn("./manifest.webmanifest?v=33", html)
        self.assertEqual(mimetypes.guess_type("manifest.webmanifest")[0], "application/manifest+json")
        self.assertIn("Literata", html)
        self.assertIn('data-mode="posters"', html)
        self.assertNotIn("statusFilterSelect", html)
        self.assertNotIn("statusFilterSelect", js)
        self.assertIsNone(re.search(r"\bstate\.tag\b", js))

        for fname in ("manifest.webmanifest", "sw.js", "icon.svg", "icon-192.png", "icon-512.png"):
            self.assertTrue((tma_dir / fname).is_file(), f"Missing PWA asset: {fname}")
        self.assertIn("notes-shell-v33", (tma_dir / "sw.js").read_text(encoding="utf-8"))
        self.assertTrue((tma_dir / "icon-192.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue((tma_dir / "icon-512.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        manifest = json.loads((tma_dir / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["share_target"]["params"]["url"], "share_url")

        # 2. Ключевые элементы и стили Этапов 1–6 (v26–v32)
        for token in (
            'id="ratingPopover"',
            'id="emptyStateActions"',
            'id="emptyStateTitle"',
            'id="emptyStateDesc"',
            'id="sidebarSmartViews"',
            'id="activeSmartBanner"',
            'id="drawerLuckyAgainBtn"',
            'id="shortcutsOverlay"',
            'id="shortcutsCloseBtn"',
            'id="shortcutsHelpBtnDesktop"',
            'id="bulkActionBar"',
            'id="bulkStatusSelect"',
            'id="bulkDeleteBtn"',
            'id="metaThemeColor"',
            'data-view="stats"',
            'id="loadMoreBar"',
            'id="loadMoreBtn"',
            'id="pullRefreshIndicator"',
            'id="globalDropOverlay"',
            'id="liveToast"',
            'value="updated"',
            'value="year"',
            'value="title"',
            'id="zenReaderOverlay"',
            'id="zenReaderScroll"',
            'id="zenReaderContent"',
            'id="zenProgressFill"',
            'id="zenSelectionBar"',
            'id="zenSaveSelectionBtn"',
            'id="zenFontDecBtn"',
            'id="zenFontIncBtn"',
            'id="zenWidthToggleBtn"',
            'id="zenManualQuoteBtn"',
        ):
            self.assertIn(token, html)

        for token in (
            '"Literata"',
            "drawer-status-pill",
            "drawer-rate-btn",
            "swipe-row-wrap",
            "swipe-tray-left",
            "swipe-tray-right",
            "swipe-tray-btn",
            "full-armed",
            "touch-action: pan-y",
            "topbar-hidden",
            "rating-popover",
            "list-mobile-actions",
            "--cat-accent-color",
            "view-posters",
            "poster-card",
            "poster-video",
            "card-video-thumb",
            "list-summary-snippet",
            "list-type-badge",
            "active-smart-banner",
            "drawer-triage-banner",
            "kb-focused",
            "shortcuts-modal",
            "drawer-lucky-btn",
            "triage-chip",
            "cmd-loading-hint",
            "chip-x",
            "bulk-action-bar",
            "bulk-select-cb",
            "stats-dashboard",
            "stats-histogram",
            "stats-diary-row",
            "content-visibility: auto",
            "active-poster",
            "load-more-bar",
            "pull-refresh-indicator",
            "global-drop-overlay",
            "live-toast",
            "vt-drawer-active",
            "detail-drawer-panel",
            "vt-source-card",
            "vt-handled",
            "zen-reader-overlay",
            "zen-progress-fill",
            "animation-timeline",
            "zen-highlight",
            "drawer-progress-card",
            "poster-progress-bar",
            "drawer-highlight-card",
            "drawer-attention-banner",
            "progress-toggle-head",
            "touch-action: pinch-zoom",
        ):
            self.assertIn(token, css)

        for token in (
            "flushPendingNoteSave",
            "syncDetailDrawerInPlace",
            "openRatingPopover",
            "closeRatingPopover",
            "renderEmptyState",
            "initMobileAutoHideTopbar",
            "swipe-row-wrap",
            "drawer-status-pill",
            "drawer-rate-btn",
            "topbar-hidden",
            "sb_view_modes_by_tab_v1",
            "getViewModeForTab",
            "renderPosterCard",
            "getSwipeRightActions",
            "closeOpenSwipeRow",
            "suppressSwipeClickUntil",
            "estimateReadingMinutes",
            "page_count",
            "startInboxTriage",
            "advanceInboxTriage",
            "toggleSmartView",
            "toggleTagFilter",
            "renderActiveSmartBanner",
            "syncStateToUrl",
            "restoreStateFromUrl",
            "fetchGlobalCmdItems",
            "moveListFocus",
            "openShortcutsModal",
            "closeShortcutsModal",
            "pickRandomItem",
            "externalDrawerItem",
            "toggleBulkSelect",
            "runBulkAction",
            "loadStats",
            "renderStats",
            "pendingShareText",
            "serviceWorker",
            "CATALOG_PAGE_SIZE",
            "quickIngestFromDropOrPaste",
            "initPullToRefresh",
            "syncTmaSafeArea",
            "hydrateFromTgCloudStorage",
            "findCatalogPosterEl",
            "clearActiveHeroTransition",
            'decoding="sync"',
            "openZenReader",
            "closeZenReader",
            "saveZenHighlight",
            "buildDrawerProgressHtml",
            "buildDrawerHighlightsHtml",
            "reenrichItemInDrawer",
            "getItemProgressSummary",
            "pushOverlayHistory",
            "popOverlayHistory",
            "bindLightboxSwipe",
            "bindDrawerHorizontalNavSwipe",
            "drawerProgressExpanded",
            "data-drawer-delete",
        ):
            self.assertIn(token, js)

        # 3. Все ID, запрашиваемые через getElementById(...) в app.js, объявлены в index.html или динамическом HTML
        declared_ids = set(re.findall(r'id="([^"]+)"', html)) | set(re.findall(r'id="([^"$]+)"', js))
        referenced_ids = set(re.findall(r'document\.getElementById\("([^"]+)"\)', js))
        missing_ids = referenced_ids - declared_ids
        self.assertEqual(missing_ids, set(), f"Missing HTML/JS IDs: {missing_ids}")

        # 4. Проверка монтирования /tma в FastAPI-приложении и корневого редиректа
        self.assertTrue(any(getattr(r, "path", "") == "/tma" for r in main_mod.app.routes))
        self.assertEqual(main_mod.root_redirect().headers.get("location"), "/tma/")


if __name__ == "__main__":
    unittest.main(verbosity=2)
