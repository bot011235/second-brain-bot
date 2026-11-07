from __future__ import annotations

import json
import re
from typing import Any

from app.clients.tmdb import TMDBClient
from app.clients.wikidata_kp import (
    build_fallback_rt_url,
    fetch_imdb_rating,
    fetch_kp_and_imdb_ratings,
    fetch_rt_score,
    guess_and_fetch_rt,
    resolve_ids_via_wikidata,
    search_wikidata_movies,
)
from app.db import repo
from app.utils.normalize import normalize_text

_TRAILING_YEAR_RE = re.compile(r"^(?P<title>.+?)\s*[\(\[]?(?P<year>(?:19|20)\d{2})[\)\]]?\s*$")
_IMDB_ID_RE = re.compile(r"(tt\d{6,10})", flags=re.IGNORECASE)
_KP_URL_RE = re.compile(r"kinopoisk\.ru/(?:film|series)/(\d+)", flags=re.IGNORECASE)
_TMDB_URL_RE = re.compile(r"themoviedb\.org/(movie|tv)/(\d+)", flags=re.IGNORECASE)


def parse_direct_media_ids(text: str) -> dict[str, Any]:
    """Извлекает прямые ID из ссылок на IMDb, Кинопоиск или TMDB, если пользователь кинул ссылку."""
    out: dict[str, Any] = {}
    m_imdb = _IMDB_ID_RE.search(text)
    if m_imdb:
        out["imdb_id"] = m_imdb.group(1).lower()
    m_kp = _KP_URL_RE.search(text)
    if m_kp:
        out["kp_id"] = int(m_kp.group(1))
    m_tmdb = _TMDB_URL_RE.search(text)
    if m_tmdb:
        out["media_type"] = m_tmdb.group(1).lower()
        out["tmdb_id"] = int(m_tmdb.group(2))
    return out


def parse_title_and_year(raw_text: str) -> tuple[str, int | None]:
    """Отделяет год в конце строки: 'Дюна 2021' -> ('Дюна', 2021)."""
    first_line = raw_text.strip().splitlines()[0].strip()
    m = _TRAILING_YEAR_RE.match(first_line)
    if m:
        title = m.group("title").strip(" -—–:")
        year = int(m.group("year"))
        if title:
            return title, year
    return first_line, None


def search_movie_candidates(
    query: str,
    year: int | None = None,
    tmdb: TMDBClient | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Ищет кандидатов через официальный TMDB API, а если ключ не задан — через официальный Wikidata API."""
    tmdb = tmdb or TMDBClient()
    direct = parse_direct_media_ids(query)
    if direct.get("tmdb_id") and direct.get("media_type") and tmdb.is_configured:
        return [tmdb.get_details(str(direct["media_type"]), int(direct["tmdb_id"]))]
    if direct.get("imdb_id"):
        if tmdb.is_configured:
            found_by_imdb = tmdb.find_by_imdb_id(str(direct["imdb_id"]))
            if found_by_imdb:
                return [found_by_imdb]
        return search_wikidata_movies(str(direct["imdb_id"]), limit=1)
    if direct.get("kp_id"):
        wd = resolve_ids_via_wikidata(kp_id=int(direct["kp_id"]))
        if wd.get("imdb_id") and tmdb.is_configured:
            found_by_kp = tmdb.find_by_imdb_id(str(wd["imdb_id"]))
            if found_by_kp:
                found_by_kp["kp_id"] = int(direct["kp_id"])
                return [found_by_kp]

    if tmdb.is_configured:
        candidates = tmdb.search_candidates(query, year=year, limit=limit)
        if candidates:
            return candidates
    return search_wikidata_movies(query, year=year, limit=limit)


def is_unambiguous_match(query: str, year: int | None, candidates: list[dict[str, Any]]) -> bool:
    """Автовыбор срабатывает только если кандидат ровно один или явно указан год и есть точное совпадение."""
    if not candidates:
        return False
    if len(candidates) == 1:
        return True
    if year is not None:
        norm_q = normalize_text(query)
        exact = [
            c
            for c in candidates
            if c.get("release_year") == year
            and (normalize_text(c.get("title_ru")) == norm_q or normalize_text(c.get("title_orig")) == norm_q)
        ]
        if len(exact) == 1:
            # Перемещаем точное совпадение на 0-ю позицию
            candidates.remove(exact[0])
            candidates.insert(0, exact[0])
            return True
    return False


def enrich_candidate(candidate: dict[str, Any], tmdb: TMDBClient | None = None) -> dict[str, Any]:
    """Дообогащает выбранного кандидата деталями из TMDB, Wikidata (kp_id, imdb_id, RT) и rating.kinopoisk.ru."""
    tmdb = tmdb or TMDBClient()
    enriched = dict(candidate)

    if tmdb.is_configured:
        if candidate.get("tmdb_id") and candidate.get("media_type"):
            details = tmdb.get_details(str(candidate["media_type"]), int(candidate["tmdb_id"]))
            enriched.update({k: v for k, v in details.items() if v is not None})
        elif candidate.get("imdb_id"):
            details_or_none = tmdb.find_by_imdb_id(str(candidate["imdb_id"]))
            if details_or_none:
                enriched.update({k: v for k, v in details_or_none.items() if v is not None})

    imdb_id = enriched.get("imdb_id")
    wikidata_id = enriched.get("wikidata_id")
    kp_id = enriched.get("kp_id")
    url_rt = enriched.get("url_rt")

    if (not kp_id or not imdb_id or not url_rt) and (imdb_id or wikidata_id):
        wd = resolve_ids_via_wikidata(imdb_id=imdb_id, wikidata_id=wikidata_id)
        imdb_id = imdb_id or wd.get("imdb_id")
        kp_id = kp_id or wd.get("kp_id")
        url_rt = url_rt or wd.get("url_rt")

    ratings = fetch_kp_and_imdb_ratings(kp_id)
    rating_kp = ratings.get("rating_kp")
    rating_imdb = ratings.get("rating_imdb") or fetch_imdb_rating(imdb_id)
    rating_rt = enriched.get("rating_rt") or fetch_rt_score(url_rt)

    if rating_rt is None and (not url_rt or "/search?" in url_rt):
        guessed_rt_url, guessed_rt_score = guess_and_fetch_rt(
            enriched.get("title_orig"),
            release_year=enriched.get("release_year"),
            category=enriched.get("category") or "movie",
        )
        if guessed_rt_url and guessed_rt_score is not None:
            url_rt = guessed_rt_url
            rating_rt = guessed_rt_score

    if not url_rt:
        url_rt = build_fallback_rt_url(enriched.get("title_orig"), enriched.get("title_ru"))

    meta: dict[str, Any] = {}
    if enriched.get("tmdb_id"):
        meta["tmdb_id"] = enriched["tmdb_id"]
    if enriched.get("wikidata_id"):
        meta["wikidata_id"] = enriched["wikidata_id"]
    if enriched.get("rating_tmdb"):
        meta["rating_tmdb"] = enriched["rating_tmdb"]

    return {
        "category": enriched.get("category") or "movie",
        "title_ru": enriched.get("title_ru") or "Без названия",
        "title_orig": enriched.get("title_orig"),
        "release_year": enriched.get("release_year"),
        "creator": enriched.get("creator"),
        "summary": enriched.get("summary"),
        "poster_url": enriched.get("poster_url"),
        "imdb_id": imdb_id,
        "kp_id": kp_id,
        "rating_imdb": rating_imdb,
        "rating_kp": rating_kp,
        "rating_rt": rating_rt,
        "url_rt": url_rt,
        "genres": enriched.get("genres") or [],
        "meta": meta,
    }


def extract_candidates_from_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    raw_meta = item.get("meta")
    if not raw_meta:
        return []
    try:
        parsed = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
        return list(parsed.get("candidates") or [])
    except Exception:
        return []
