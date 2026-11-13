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

_URL_ONLY_RE = re.compile(r"^https?://\S+$", flags=re.IGNORECASE)
_INLINE_URL_RE = re.compile(r"https?://\S+", flags=re.IGNORECASE)
_TRAILING_YEAR_RE = re.compile(r"^(?P<title>.+?)\s*(?:,\s*)?[\(\[]?(?P<year>(?:19|20)\d{2})(?:\s*[–-]\s*(?:(?:19|20)\d{2})?)?[\)\]]?\s*$")
_SHARE_SITE_SUFFIX_RE = re.compile(
    r"\s*(?:[—–|-]\s*(?:Кинопоиск|Kinopoisk|IMDb|TMDB|The Movie Database(?:\s*\(TMDB\))?)|на\s+Кинопоиске)\s*$",
    flags=re.IGNORECASE,
)
_KP_SEO_TAIL_RE = re.compile(
    r"(?:[,—–-]\s*|\s+)(?:описание,\s*интересные факты|дата выхода\s+трейлеры.*|смотреть онлайн.*)$",
    flags=re.IGNORECASE,
)
_KP_PAREN_KIND_RE = re.compile(r"\s*\((?:(?:мини-)?сериал|ТВ|фильм)\b[^)]*\)", flags=re.IGNORECASE)
_KP_WORD_KIND_SUFFIX_RE = re.compile(r"\s+(?:фильм|(?:мини-)?сериал)\s*$", flags=re.IGNORECASE)
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
    """Отделяет год и очищает SEO-хвосты браузерного шаринга (Кинопоиск/IMDb/TMDB)."""
    lines = [ln.strip() for ln in raw_text.strip().splitlines() if ln.strip()]
    if not lines:
        return "", None
    first_line = next((ln for ln in lines if not _URL_ONLY_RE.match(ln)), lines[0])
    cleaned = _INLINE_URL_RE.sub("", first_line).strip() or first_line

    had_share_seo = False
    for pattern in (_SHARE_SITE_SUFFIX_RE, _KP_SEO_TAIL_RE, _SHARE_SITE_SUFFIX_RE):
        updated = pattern.sub("", cleaned).strip(" ,—–-")
        if updated != cleaned:
            had_share_seo = True
            cleaned = updated

    updated_paren = _KP_PAREN_KIND_RE.sub("", cleaned).strip(" ,—–-")
    if updated_paren != cleaned:
        had_share_seo = True
        cleaned = updated_paren

    m = _TRAILING_YEAR_RE.match(cleaned)
    if m:
        title = m.group("title").strip(" ,-—–:")
        year = int(m.group("year"))
        if had_share_seo:
            title = _KP_WORD_KIND_SUFFIX_RE.sub("", title).strip(" ,-—–:")
        if title:
            return title, year
    if had_share_seo:
        cleaned = _KP_WORD_KIND_SUFFIX_RE.sub("", cleaned).strip(" ,-—–:")
    return cleaned, None


def search_movie_candidates(
    query: str,
    year: int | None = None,
    tmdb: TMDBClient | None = None,
    limit: int = 3,
    title_orig: str | None = None,
    raw_text: str | None = None,
) -> list[dict[str, Any]]:
    """Ищет кандидатов через официальный TMDB API, а если ключ не задан — через официальный Wikidata API."""
    tmdb = tmdb or TMDBClient()
    direct = parse_direct_media_ids(raw_text or query)
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

    # Извлечение оригинального названия из скобок, если есть: 'Полые деревья (Hollow Trees)'
    match_paren = re.search(r"\(([^)]+)\)", query)
    paren_title = match_paren.group(1).strip() if match_paren else None
    clean_query = re.sub(r"\([^)]+\)", "", query).strip() or query
    if not title_orig and paren_title and re.search(r"[a-zA-Z]", paren_title):
        title_orig = paren_title

    queries_to_try: list[tuple[str, int | None]] = []
    # 1. Основной запрос с годом
    queries_to_try.append((clean_query, year))
    # 2. Оригинальное название с годом
    if title_orig and title_orig.strip().lower() != clean_query.lower():
        queries_to_try.append((title_orig.strip(), year))
    # 3. Подзаголовки через точку/двоеточие/тире ('Дримквилл. Корпорация мечты' -> 'Дримквилл')
    for sep in [".", ":", " — ", " - "]:
        if sep in clean_query:
            prefix = clean_query.split(sep)[0].strip()
            if len(prefix) >= 3 and prefix.lower() != clean_query.lower():
                queries_to_try.append((prefix, year))
    # 4. Без года, если год был указан (часто релизы сдвигаются)
    if year is not None:
        queries_to_try.append((clean_query, None))
        if title_orig and title_orig.strip().lower() != clean_query.lower():
            queries_to_try.append((title_orig.strip(), None))

    if not clean_query or _URL_ONLY_RE.match(clean_query):
        return []

    def _with_direct_kp(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if direct.get("kp_id"):
            for item in items:
                item.setdefault("kp_id", int(direct["kp_id"]))
        return items

    if tmdb.is_configured:
        seen_ids: set[tuple[str, int]] = set()
        for q, yr in queries_to_try:
            candidates = tmdb.search_candidates(q, year=yr, limit=limit)
            if candidates:
                unique = []
                for c in candidates:
                    key = (c.get("media_type", "movie"), c.get("tmdb_id") or 0)
                    if key not in seen_ids:
                        seen_ids.add(key)
                        unique.append(c)
                if unique:
                    return _with_direct_kp(unique)

    candidates = search_wikidata_movies(clean_query, year=year, limit=limit)
    if not candidates and title_orig:
        candidates = search_wikidata_movies(title_orig, year=year, limit=limit)
    return _with_direct_kp(candidates)


def is_unambiguous_match(
    query: str,
    year: int | None,
    candidates: list[dict[str, Any]],
    title_orig: str | None = None,
) -> bool:
    """Автовыбор срабатывает только если кандидат ровно один, либо есть точное совпадение по title_orig/году."""
    if not candidates:
        return False
    if len(candidates) == 1:
        return True

    # Если есть оригинальное название на латинице (например 'Hollow Trees' или 'DreamQuil')
    if title_orig:
        norm_orig = normalize_text(title_orig)
        exact_orig = [c for c in candidates if normalize_text(c.get("title_orig")) == norm_orig]
        if len(exact_orig) == 1:
            candidates.remove(exact_orig[0])
            candidates.insert(0, exact_orig[0])
            return True

    # Если явно указан год и есть ровно одно совпадение по названию и году
    if year is not None:
        norm_q = normalize_text(query)
        exact = [
            c
            for c in candidates
            if c.get("release_year") == year
            and (normalize_text(c.get("title_ru")) == norm_q or normalize_text(c.get("title_orig")) == norm_q)
        ]
        if len(exact) == 1:
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
    if enriched.get("seasons_count"):
        meta["seasons_count"] = int(enriched["seasons_count"])

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
