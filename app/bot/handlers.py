from __future__ import annotations

import re
from typing import Any

from app.bot.cards import format_status_label, render_card_html
from app.bot.keyboards import build_item_keyboard
from app.bot.telegram_api import TelegramClient
from app.clients.books import BooksClient
from app.clients.groq_llm import GroqLLMClient, extract_hashtags
from app.clients.scraper import scrape_url
from app.clients.tmdb import TMDBClient
from app.clients.youtube import YouTubeClient
from app.config import settings
from app.db import repo
from app.pipeline import books as books_pipeline
from app.pipeline import movies as movies_pipeline
from app.utils.urls import normalize_url

_URL_RE = re.compile(r"https?://\S+", flags=re.IGNORECASE)
_LIST_PREFIX_RE = re.compile(r"^\s*(?:\d+[\.\)\-:]|[-•*—–])\s*")


def split_batch_lines(text: str) -> list[str]:
    """Разбивает многострочный список книг/фильмов на отдельные запросы (убирая нумерацию и буллиты)."""
    items: list[str] = []
    for raw_line in text.splitlines():
        cleaned = _LIST_PREFIX_RE.sub("", raw_line).strip()
        if cleaned:
            items.append(cleaned)
    return items

TOPIC_TO_DEFAULT_CATEGORY: dict[str, str] = {
    "movies": "movie",
    "books": "book",
    "youtube": "video",
    "articles": "article",
    "ideas": "idea",
    "general": "idea",
}


def infer_category(topic_name: str, text: str) -> tuple[str, str | None, str]:
    """Определяет (category, first_url, source_type) по топику и тексту сообщения."""
    match = _URL_RE.search(text)
    url = match.group(0) if match else None

    source_type = "manual"
    if url:
        low = url.lower()
        if "youtu.be" in low or "youtube.com" in low:
            source_type = "youtube"
        elif "threads.net" in low or "threads.com" in low:
            source_type = "threads"
        elif "instagram.com" in low:
            source_type = "instagram"
        else:
            source_type = "web"

    if topic_name in ("movies", "books", "youtube", "articles", "ideas"):
        return TOPIC_TO_DEFAULT_CATEGORY[topic_name], url, source_type

    if url:
        if source_type == "youtube":
            return "video", url, source_type
        if source_type in ("threads", "instagram"):
            return "post", url, source_type
        return "article", url, source_type
    return "idea", None, "manual"


def _is_authorized(chat_id: int | None, user_id: int | None) -> bool:
    if settings.tg_chat_id and chat_id != settings.tg_chat_id:
        return False
    if settings.allowed_tg_user_id and user_id != settings.allowed_tg_user_id:
        return False
    return True


def handle_update(
    conn: Any,
    update: dict[str, Any],
    tg: TelegramClient | None = None,
    tmdb: TMDBClient | None = None,
    books_client: BooksClient | None = None,
) -> dict[str, Any]:
    """Единая точка обработки Telegram Update (и для Webhook, и для Long Polling)."""
    tg = tg or TelegramClient()
    update_id = update.get("update_id")
    if update_id is not None and not repo.mark_update_processed(conn, int(update_id)):
        return {"status": "duplicate_update", "update_id": update_id}

    if "message" in update:
        return _handle_message(conn, update["message"], tg, tmdb=tmdb, books_client=books_client)
    if "callback_query" in update:
        return _handle_callback(conn, update["callback_query"], tg, tmdb=tmdb)
    return {"status": "ignored"}


def _publish_and_replace(
    conn: Any,
    tg: TelegramClient,
    item: dict[str, Any],
    chat_id: int | None,
    thread_id: int | None,
    user_msg_id: int | None,
) -> None:
    # Сохраняем user_msg_id как tg_message_id, чтобы ссылка "В чате" вела на сообщение пользователя
    if user_msg_id:
        repo.set_item_tg_message_id(conn, item["id"], int(user_msg_id))
        item["tg_message_id"] = int(user_msg_id)
        if chat_id and settings.telegram_bot_token:
            try:
                tg.set_message_reaction(chat_id, int(user_msg_id), "👍")
            except Exception:
                pass


def _resolve_original_topic_slug(topic_name: str, category: str) -> str:
    if topic_name == "movies" or category in ("movie", "series"):
        return "movies"
    if topic_name == "books" or category == "book":
        return "books"
    if topic_name == "youtube" or category == "video":
        return "video"
    if topic_name == "articles" or category == "article":
        return "article"
    return "ideas"


def _record_original_message(
    conn: Any,
    *,
    topic_name: str,
    category: str,
    raw_text: str,
    thread_id: int | None = None,
    msg_id: int | None = None,
    source_url: str | None = None,
    source_type: str = "manual",
    author: str | None = None,
    extracted_text: str | None = None,
) -> None:
    try:
        repo.create_original_message(
            conn,
            topic_slug=_resolve_original_topic_slug(topic_name, category),
            raw_text=raw_text,
            tg_topic_id=thread_id,
            tg_message_id=msg_id,
            source_url=source_url,
            source_type=source_type,
            author=author,
            extracted_text=extracted_text,
        )
    except Exception:
        pass


def _handle_movie_text(
    conn: Any,
    text: str,
    chat_id: int | None,
    thread_id: int | None,
    user_msg_id: int | None,
    tg: TelegramClient,
    tmdb: TMDBClient | None = None,
    source_url: str | None = None,
    source_type: str = "manual",
    title_orig: str | None = None,
) -> dict[str, Any]:
    query, year = movies_pipeline.parse_title_and_year(text)
    candidates = movies_pipeline.search_movie_candidates(
        query, year=year, tmdb=tmdb, limit=3, title_orig=title_orig, raw_text=text
    )

    if not candidates:
        item = repo.create_item(
            conn,
            category="movie",
            title_ru=query,
            title_orig=title_orig,
            release_year=year,
            raw_input=text,
            processing_status="needs_input",
            tg_topic_id=thread_id,
            source_url=source_url,
            source_type=source_type,
        )
        _publish_and_replace(conn, tg, item, chat_id, thread_id, user_msg_id)
        return {"status": "needs_input", "item_id": item["id"]}

    if movies_pipeline.is_unambiguous_match(query, year, candidates, title_orig=title_orig):
        enriched = movies_pipeline.enrich_candidate(candidates[0], tmdb=tmdb)
        existing = repo.find_existing_movie(
            conn,
            kp_id=enriched.get("kp_id"),
            imdb_id=enriched.get("imdb_id"),
            title_ru=enriched.get("title_ru"),
            release_year=enriched.get("release_year"),
        )
        if existing:
            repo.add_source_to_item(conn, existing["id"], source_url=source_url, source_type=source_type, raw_text=text)
            if chat_id and user_msg_id and settings.telegram_bot_token:
                try:
                    tg.set_message_reaction(chat_id, int(user_msg_id), "👍")
                except Exception:
                    pass
            return {"status": "duplicate_item", "item_id": existing["id"]}

        item = repo.create_item(
            conn,
            category=enriched["category"],
            title_ru=enriched["title_ru"],
            title_orig=enriched.get("title_orig"),
            release_year=enriched.get("release_year"),
            creator=enriched.get("creator"),
            summary=enriched.get("summary"),
            poster_url=enriched.get("poster_url"),
            imdb_id=enriched.get("imdb_id"),
            kp_id=enriched.get("kp_id"),
            rating_imdb=enriched.get("rating_imdb"),
            rating_kp=enriched.get("rating_kp"),
            rating_rt=enriched.get("rating_rt"),
            url_rt=enriched.get("url_rt"),
            genres=enriched.get("genres"),
            meta=enriched.get("meta"),
            raw_input=text,
            processing_status="ok",
            tg_topic_id=thread_id,
            source_url=source_url,
            source_type=source_type,
        )
        _publish_and_replace(conn, tg, item, chat_id, thread_id, user_msg_id)
        return {"status": "created", "item_id": item["id"], "category": item["category"]}

    item = repo.create_item(
        conn,
        category="movie",
        title_ru=query,
        release_year=year,
        raw_input=text,
        processing_status="needs_choice",
        meta={"candidates": candidates[:3]},
        tg_topic_id=thread_id,
        source_url=source_url,
        source_type=source_type,
    )
    _publish_and_replace(conn, tg, item, chat_id, thread_id, user_msg_id)
    return {"status": "needs_choice", "item_id": item["id"], "candidates": len(candidates[:3])}


def _handle_book_text(
    conn: Any,
    text: str,
    chat_id: int | None,
    thread_id: int | None,
    user_msg_id: int | None,
    tg: TelegramClient,
    books_client: BooksClient | None = None,
    source_url: str | None = None,
    source_type: str = "manual",
) -> dict[str, Any]:
    query = text.splitlines()[0].strip()
    candidates = books_pipeline.search_book_candidates(query, books_client=books_client, limit=3)

    if not candidates:
        item = repo.create_item(
            conn,
            category="book",
            title_ru=query,
            raw_input=text,
            processing_status="needs_input",
            tg_topic_id=thread_id,
            source_url=source_url,
            source_type=source_type,
        )
        _publish_and_replace(conn, tg, item, chat_id, thread_id, user_msg_id)
        return {"status": "needs_input", "item_id": item["id"]}

    if books_pipeline.is_unambiguous_book_match(query, candidates):
        enriched = books_pipeline.enrich_book_candidate(candidates[0])
        existing = repo.find_existing_book(
            conn,
            google_books_id=enriched.get("google_books_id"),
            title_ru=enriched.get("title_ru"),
            creator=enriched.get("creator"),
        )
        if existing:
            repo.add_source_to_item(conn, existing["id"], source_url=source_url, source_type=source_type, raw_text=text)
            if chat_id and user_msg_id and settings.telegram_bot_token:
                try:
                    tg.set_message_reaction(chat_id, int(user_msg_id), "👍")
                except Exception:
                    pass
            return {"status": "duplicate_item", "item_id": existing["id"]}

        item = repo.create_item(
            conn,
            category="book",
            title_ru=enriched["title_ru"],
            title_orig=enriched.get("title_orig"),
            release_year=enriched.get("release_year"),
            creator=enriched.get("creator"),
            summary=enriched.get("summary"),
            poster_url=enriched.get("poster_url"),
            google_books_id=enriched.get("google_books_id"),
            isbn13=enriched.get("isbn13"),
            rating_kp=enriched.get("rating_kp"),
            rating_imdb=enriched.get("rating_imdb"),
            genres=enriched.get("genres"),
            meta=enriched.get("meta"),
            raw_input=text,
            processing_status="ok",
            tg_topic_id=thread_id,
            source_url=source_url,
            source_type=source_type,
        )
        _publish_and_replace(conn, tg, item, chat_id, thread_id, user_msg_id)
        return {"status": "created", "item_id": item["id"], "category": "book"}

    item = repo.create_item(
        conn,
        category="book",
        title_ru=query,
        raw_input=text,
        processing_status="needs_choice",
        meta={"candidates": candidates[:3]},
        tg_topic_id=thread_id,
        source_url=source_url,
        source_type=source_type,
    )
    _publish_and_replace(conn, tg, item, chat_id, thread_id, user_msg_id)
    return {"status": "needs_choice", "item_id": item["id"], "candidates": len(candidates[:3])}


def _handle_message(
    conn: Any,
    msg: dict[str, Any],
    tg: TelegramClient,
    tmdb: TMDBClient | None = None,
    books_client: BooksClient | None = None,
) -> dict[str, Any]:
    chat_id = msg.get("chat", {}).get("id")
    user_id = msg.get("from", {}).get("id")
    if not _is_authorized(chat_id, user_id):
        return {"status": "unauthorized"}

    text = (msg.get("text") or msg.get("caption") or "").strip()
    if not text:
        return {"status": "empty_message"}

    thread_id = msg.get("message_thread_id")
    msg_id = msg.get("message_id")
    topic_name = settings.resolve_topic_name(thread_id)
    category, url, source_type = infer_category(topic_name, text)

    # Этап 2: запросы в топике Movies (поддерживает и 1 фильм, и список фильмов построчно)
    if topic_name == "movies" and (not url or movies_pipeline.parse_direct_media_ids(text)):
        _record_original_message(
            conn,
            topic_name=topic_name,
            category="movie",
            raw_text=text,
            thread_id=thread_id,
            msg_id=msg_id,
            source_url=url,
            source_type=source_type,
        )
        lines = split_batch_lines(text) if not url else [text]
        if len(lines) > 1:
            results = [
                _handle_movie_text(conn, line, chat_id, thread_id, None, tg, tmdb=tmdb)
                for line in lines
            ]
            if chat_id and msg_id and settings.telegram_bot_token:
                try:
                    tg.set_message_reaction(chat_id, int(msg_id), "👍")
                except Exception:
                    pass
            return {"status": "batch_created", "count": len(results), "results": results}
        return _handle_movie_text(
            conn,
            lines[0] if lines else text,
            chat_id,
            thread_id,
            msg_id,
            tg,
            tmdb=tmdb,
            source_url=url,
            source_type=source_type,
        )

    # Этап 3: запросы в топике Books (поддерживает и 1 книгу, и список книг построчно)
    if topic_name == "books" and not url:
        _record_original_message(
            conn,
            topic_name=topic_name,
            category="book",
            raw_text=text,
            thread_id=thread_id,
            msg_id=msg_id,
            source_type="manual",
        )
        lines = split_batch_lines(text)
        if len(lines) > 1:
            results = [
                _handle_book_text(conn, line, chat_id, thread_id, None, tg, books_client=books_client)
                for line in lines
            ]
            if chat_id and msg_id and settings.telegram_bot_token:
                try:
                    tg.set_message_reaction(chat_id, int(msg_id), "👍")
                except Exception:
                    pass
            return {"status": "batch_created", "count": len(results), "results": results}
        return _handle_book_text(conn, lines[0] if lines else text, chat_id, thread_id, msg_id, tg, books_client=books_client)

    title_line = text.splitlines()[0][:120]
    summary = text if len(text) > len(title_line) else None
    poster_url: str | None = None
    creator: str | None = None
    release_year: int | None = None
    tags: list[str] = []
    processing_status = "ok"
    canonical_url = normalize_url(url) if url else None

    # Этап 4: дедупликация и обогащение ссылок (YouTube, статьи, посты, подборки)
    if canonical_url:
        # Извлекаем метаданные страницы или YouTube-видео (включая редиректы share-ссылок Threads)
        if source_type == "youtube":
            yt_info = YouTubeClient().fetch_video_info(canonical_url)
            raw_title = yt_info.get("title")
            raw_desc = yt_info.get("description")
            creator = yt_info.get("creator")
            release_year = yt_info.get("release_year")
            poster_url = yt_info.get("poster_url")
            tags = list(yt_info.get("tags") or [])
        else:
            scraped = scrape_url(canonical_url)
            canonical_url = scraped.get("canonical_url") or canonical_url
            raw_title = scraped.get("title")
            raw_desc = scraped.get("text") or scraped.get("description")
            creator = scraped.get("author")
            poster_url = scraped.get("poster_url")
            if not scraped.get("ok") and text.strip() == url.strip():
                processing_status = "needs_input"

        _record_original_message(
            conn,
            topic_name=topic_name,
            category=category,
            raw_text=text,
            thread_id=thread_id,
            msg_id=msg_id,
            source_url=canonical_url,
            source_type=source_type,
            author=creator,
            extracted_text=raw_desc or raw_title,
        )

        if topic_name not in ("movies", "books"):
            existing_url_item = repo.find_existing_by_url(conn, canonical_url)
            if existing_url_item:
                repo.add_source_to_item(
                    conn,
                    existing_url_item["id"],
                    source_url=canonical_url,
                    source_type=source_type,
                    raw_text=raw_desc or text,
                )
                if chat_id and msg_id and settings.telegram_bot_token:
                    try:
                        tg.set_message_reaction(chat_id, int(msg_id), "👍")
                    except Exception:
                        pass
                return {"status": "duplicate_item", "item_id": existing_url_item["id"]}

        llm = GroqLLMClient()
        combined_context = "\n".join(p for p in (text, raw_title, raw_desc) if p)

        # Если ссылка кинута в Movies или Books — пытаемся вытащить подборку фильмов/книг через LLM
        if topic_name in ("movies", "books") and llm.is_configured and combined_context:
            media_kind = "movie" if topic_name == "movies" else "book"
            extracted = llm.extract_media_list(combined_context, media_kind=media_kind)
            if extracted:
                results = []
                for entry in extracted:
                    t_title = entry.get("title")
                    t_orig = entry.get("title_orig")
                    t_year = entry.get("year")
                    q_str = f"{t_title} {t_year}" if t_year else str(t_title)
                    if topic_name == "movies":
                        r = _handle_movie_text(
                            conn,
                            q_str,
                            chat_id,
                            thread_id,
                            None,
                            tg,
                            tmdb=tmdb,
                            source_url=canonical_url,
                            source_type=source_type,
                            title_orig=t_orig,
                        )
                    else:
                        r = _handle_book_text(
                            conn,
                            q_str,
                            chat_id,
                            thread_id,
                            None,
                            tg,
                            books_client=books_client,
                            source_url=canonical_url,
                            source_type=source_type,
                        )
                    results.append(r)
                if chat_id and msg_id and settings.telegram_bot_token:
                    try:
                        tg.set_message_reaction(chat_id, int(msg_id), "👍")
                    except Exception:
                        pass
                return {"status": "collection_extracted", "count": len(results), "results": results}
            # Если из ссылки не удалось извлечь ни одного фильма/книги, сохраняем как пост/статью/видео
            category = "post" if source_type in ("threads", "instagram") else ("video" if source_type == "youtube" else "article")

        # Обычная ссылка (YouTube / статья / пост): делаем выжимку и теги
        existing_tags = repo.list_existing_tags(conn)
        user_note = _URL_RE.sub("", text).strip()
        llm_text_parts = [p for p in (user_note, raw_desc) if p]
        llm_input_text = "\n\n".join(llm_text_parts) if llm_text_parts else text
        llm_res = llm.summarize_and_tag(title=raw_title, text=llm_input_text, existing_tags=existing_tags)
        title_line = llm_res.get("title_ru") or raw_title or title_line
        summary = llm_res.get("summary") or raw_desc

        # Сначала русскоязычные теги от LLM, затем (если есть) теги источника (YouTube) и хештеги
        merged_tags: list[str] = []
        for candidate_tag in [*(llm_res.get("tags") or []), *tags, *extract_hashtags(llm_input_text)]:
            clean_t = str(candidate_tag).lstrip("#").strip().lower()
            if clean_t and clean_t not in merged_tags:
                merged_tags.append(clean_t)
        tags = merged_tags[:6]
    else:
        _record_original_message(
            conn,
            topic_name=topic_name,
            category=category,
            raw_text=text,
            thread_id=thread_id,
            msg_id=msg_id,
            source_type="manual",
        )
        tags = extract_hashtags(text)
        if category == "idea" and settings.llm_for_ideas:
            llm = GroqLLMClient()
            if llm.is_configured and len(text.strip()) >= 5:
                existing_tags = repo.list_existing_tags(conn)
                llm_res = llm.summarize_and_tag(title=None, text=text, existing_tags=existing_tags)
                if len(text) > 80:
                    title_line = llm_res.get("title_ru") or title_line
                    summary = llm_res.get("summary") or summary
                for t in llm_res.get("tags") or []:
                    clean_t = str(t).lstrip("#").strip().lower()
                    if clean_t and clean_t not in tags:
                        tags.append(clean_t)
                tags = tags[:6]

    item = repo.create_item(
        conn,
        category=category,
        title_ru=title_line,
        raw_input=text,
        summary=summary,
        creator=creator,
        release_year=release_year,
        poster_url=poster_url,
        canonical_url=canonical_url,
        tags=tags,
        processing_status=processing_status,
        tg_topic_id=thread_id,
        source_url=canonical_url,
        source_type=source_type,
    )
    _publish_and_replace(conn, tg, item, chat_id, thread_id, msg_id)
    return {"status": "created", "item_id": item["id"], "category": category}


def _handle_callback(
    conn: Any,
    cb: dict[str, Any],
    tg: TelegramClient,
    tmdb: TMDBClient | None = None,
) -> dict[str, Any]:
    cb_id = cb.get("id", "")
    msg = cb.get("message") or {}
    chat_id = msg.get("chat", {}).get("id")
    msg_id = msg.get("message_id")
    user_id = (cb.get("from") or {}).get("id")

    if not _is_authorized(chat_id, user_id):
        if cb_id and settings.telegram_bot_token:
            tg.answer_callback_query(cb_id, "Нет доступа")
        return {"status": "unauthorized"}

    data = cb.get("data") or ""
    if data.startswith("pick:"):
        _, raw_id, choice = data.split(":", 2)
        item_id = int(raw_id)
        item = repo.get_item(conn, item_id)
        if not item:
            return {"status": "not_found"}

        if choice == "none":
            updated = repo.update_item_enriched(
                conn,
                item_id,
                category=item["category"],
                title_ru=item.get("raw_input") or item.get("title_ru") or "Без названия",
                processing_status="needs_input",
            )
            if updated and chat_id and msg_id and settings.telegram_bot_token:
                tg.edit_message_text(
                    chat_id,
                    int(msg_id),
                    render_card_html(updated),
                    reply_markup=build_item_keyboard(updated),
                )
                if cb_id:
                    tg.answer_callback_query(cb_id, "Уточните название")
            return {"status": "needs_input", "item_id": item_id}

        candidates = movies_pipeline.extract_candidates_from_item(item)
        idx = int(choice)
        if idx < 0 or idx >= len(candidates):
            return {"status": "invalid_choice"}

        chosen = candidates[idx]
        if chosen.get("category") == "book" or item.get("category") == "book":
            enriched = books_pipeline.enrich_book_candidate(chosen)
            existing = repo.find_existing_book(
                conn,
                google_books_id=enriched.get("google_books_id"),
                title_ru=enriched.get("title_ru"),
                creator=enriched.get("creator"),
                exclude_item_id=item_id,
            )
        else:
            enriched = movies_pipeline.enrich_candidate(chosen, tmdb=tmdb)
            existing = repo.find_existing_movie(
                conn,
                kp_id=enriched.get("kp_id"),
                imdb_id=enriched.get("imdb_id"),
                title_ru=enriched.get("title_ru"),
                release_year=enriched.get("release_year"),
                exclude_item_id=item_id,
            )

        if existing:
            repo.add_source_to_item(
                conn,
                existing["id"],
                source_url=None,
                source_type="manual",
                raw_text=item.get("raw_input"),
            )
            repo.delete_item(conn, item_id)
            if chat_id and msg_id and settings.telegram_bot_token:
                tg.edit_message_text(
                    chat_id,
                    int(msg_id),
                    f"🔁 Уже есть в базе: <b>{existing.get('title_ru')}</b>",
                )
                if cb_id:
                    tg.answer_callback_query(cb_id, "Уже в базе")
            return {"status": "duplicate_item", "item_id": existing["id"]}

        updated = repo.update_item_enriched(
            conn,
            item_id,
            category=enriched["category"],
            title_ru=enriched["title_ru"],
            title_orig=enriched.get("title_orig"),
            release_year=enriched.get("release_year"),
            creator=enriched.get("creator"),
            summary=enriched.get("summary"),
            poster_url=enriched.get("poster_url"),
            imdb_id=enriched.get("imdb_id"),
            kp_id=enriched.get("kp_id"),
            google_books_id=enriched.get("google_books_id"),
            isbn13=enriched.get("isbn13"),
            rating_imdb=enriched.get("rating_imdb"),
            rating_kp=enriched.get("rating_kp"),
            rating_rt=enriched.get("rating_rt"),
            url_rt=enriched.get("url_rt"),
            genres=enriched.get("genres"),
            meta=enriched.get("meta"),
            processing_status="ok",
        )
        if updated and chat_id and msg_id and settings.telegram_bot_token:
            tg.edit_message_text(
                chat_id,
                int(msg_id),
                render_card_html(updated),
                reply_markup=build_item_keyboard(updated),
            )
            if cb_id:
                tg.answer_callback_query(cb_id, f"Выбрано: {updated['title_ru']}")
        return {"status": "enriched", "item_id": item_id, "category": enriched["category"]}

    if data.startswith("st:"):
        _, raw_id, new_status = data.split(":", 2)
        item = repo.update_item_status(conn, int(raw_id), new_status)
        if item and chat_id and msg_id and settings.telegram_bot_token:
            tg.edit_message_text(
                chat_id,
                int(msg_id),
                render_card_html(item),
                reply_markup=build_item_keyboard(item),
            )
            if cb_id:
                tg.answer_callback_query(cb_id, f"Статус: {format_status_label(item['category'], new_status)}")
        return {"status": "status_updated", "item_id": int(raw_id), "new_status": new_status}

    if data.startswith("del:"):
        _, raw_id = data.split(":", 1)
        repo.delete_item(conn, int(raw_id))
        if chat_id and msg_id and settings.telegram_bot_token:
            tg.delete_message(chat_id, int(msg_id))
            if cb_id:
                tg.answer_callback_query(cb_id, "Удалено из базы")
        return {"status": "deleted", "item_id": int(raw_id)}

    return {"status": "unknown_callback"}
