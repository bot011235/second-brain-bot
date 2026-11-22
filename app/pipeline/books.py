from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.clients.books import (
    BooksClient,
    _author_similarity,
    _title_similarity,
    fetch_fantlab_info,
    fetch_fantlab_work_details,
    fetch_goodreads_info,
    parse_book_query,
)
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
    parsed_title, parsed_author, _ = parse_book_query(query)
    norm_q = normalize_text(query, strip_articles=False)
    top = candidates[0]
    norm_title = normalize_text(top.get("title_ru"), strip_articles=False)
    norm_creator = normalize_text(top.get("creator"), strip_articles=False)
    if norm_title and norm_creator and norm_title in norm_q and norm_creator in norm_q:
        return True
    if parsed_author and norm_creator:
        a_sim = _author_similarity(parsed_author, top.get("creator"))
        t_sim = _title_similarity(parsed_title, top)
        if a_sim >= 0.72 and t_sim >= 0.65:
            return True
    return False


def enrich_book_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    title_ru = candidate.get("title_ru") or "Без названия"
    title_orig = candidate.get("title_orig")
    creator = candidate.get("creator")

    fl_id_raw = candidate.get("fantlab_id")
    fl_id: int | None = int(fl_id_raw) if fl_id_raw else None
    if not fl_id:
        gb_id = str(candidate.get("google_books_id") or "")
        if gb_id.startswith("fl:") and gb_id[3:].isdigit():
            fl_id = int(gb_id[3:])

    with ThreadPoolExecutor(max_workers=2) as pool:
        if fl_id:
            fl_future = pool.submit(fetch_fantlab_work_details, fl_id)
        else:
            fl_future = pool.submit(fetch_fantlab_info, title_ru, creator=creator)
        gr_future = pool.submit(fetch_goodreads_info, title_orig, title_ru, creator=creator)
        fl_info = fl_future.result() or {}
        gr_info = gr_future.result() or {}

    if not title_orig and fl_info.get("title_orig"):
        title_orig = fl_info.get("title_orig")
        if not gr_info.get("rating_goodreads") and title_orig:
            retry_gr = fetch_goodreads_info(title_orig, title_ru, creator=creator)
            if retry_gr:
                gr_info = {**gr_info, **{k: v for k, v in retry_gr.items() if v is not None}}

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
    poster_url = candidate.get("poster_url") or fl_info.get("poster_url")
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
        "poster_url": poster_url,
        "google_books_id": candidate.get("google_books_id"),
        "isbn13": candidate.get("isbn13"),
        # Дублируем в rating_kp / rating_imdb для единой сортировки по рейтингу в БД
        "rating_kp": rating_fantlab,
        "rating_imdb": rating_goodreads,
        "genres": genres,
        "meta": meta,
    }
