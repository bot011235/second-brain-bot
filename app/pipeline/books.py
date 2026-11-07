from __future__ import annotations

from typing import Any

from app.clients.books import BooksClient, fetch_fantlab_info, fetch_goodreads_info
from app.utils.normalize import normalize_text


def search_book_candidates(
    query: str,
    books_client: BooksClient | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    books_client = books_client or BooksClient()
    return books_client.search_candidates(query, limit=limit)


def is_unambiguous_book_match(query: str, candidates: list[dict[str, Any]]) -> bool:
    if not candidates:
        return False
    if len(candidates) == 1:
        return True
    norm_q = normalize_text(query, strip_articles=False)
    top = candidates[0]
    norm_title = normalize_text(top.get("title_ru"), strip_articles=False)
    norm_creator = normalize_text(top.get("creator"), strip_articles=False)
    if norm_title and norm_creator and norm_title in norm_q and norm_creator in norm_q:
        return True
    return False


def enrich_book_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    title_ru = candidate.get("title_ru") or "Без названия"
    title_orig = candidate.get("title_orig")
    creator = candidate.get("creator")

    fl_info = fetch_fantlab_info(title_ru, creator=creator)
    gr_info = fetch_goodreads_info(title_orig, title_ru, creator=creator)

    rating_fantlab = candidate.get("rating_fantlab") or fl_info.get("rating_fantlab")
    url_fantlab = candidate.get("url_fantlab") or fl_info.get("url_fantlab")
    rating_goodreads = gr_info.get("rating_goodreads")
    url_goodreads = gr_info.get("url_goodreads")

    meta: dict[str, Any] = {}
    if candidate.get("page_count"):
        meta["page_count"] = candidate["page_count"]
    if candidate.get("info_link"):
        meta["info_link"] = candidate["info_link"]
    if rating_fantlab is not None:
        meta["rating_fantlab"] = rating_fantlab
    if url_fantlab:
        meta["url_fantlab"] = url_fantlab
    if rating_goodreads is not None:
        meta["rating_goodreads"] = rating_goodreads
    if url_goodreads:
        meta["url_goodreads"] = url_goodreads

    summary = candidate.get("summary") or fl_info.get("summary")
    genres = list(candidate.get("genres") or [])
    for g in fl_info.get("genres") or []:
        if g not in genres:
            genres.append(g)

    return {
        "category": "book",
        "title_ru": title_ru,
        "title_orig": title_orig,
        "release_year": candidate.get("release_year"),
        "creator": creator,
        "summary": summary,
        "poster_url": candidate.get("poster_url"),
        "google_books_id": candidate.get("google_books_id"),
        "isbn13": candidate.get("isbn13"),
        # Дублируем в rating_kp / rating_imdb для единой сортировки по рейтингу в БД
        "rating_kp": rating_fantlab,
        "rating_imdb": rating_goodreads,
        "genres": genres,
        "meta": meta,
    }
