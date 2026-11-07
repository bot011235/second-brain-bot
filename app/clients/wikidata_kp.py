from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote_plus

import httpx

WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIDATA_USER_AGENT = "PersonalSecondBrainBot/0.4 (https://github.com/personal-db; bot)"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
_RT_SCORE_RE = re.compile(r"criticsScore[^>]*>\s*(\d{1,3})%|\"ratingValue\"\s*:\s*\"?(\d{1,3})\"?")

# P31 (instance of) Q-IDs для определения типа (фильм / сериал) при резервном поиске через Wikidata
_SERIES_QIDS = {
    "Q5398426",   # television series
    "Q1259759",   # miniseries
    "Q63952888",  # anime television series
    "Q526877",    # web series
}
_MOVIE_QIDS = {
    "Q11424",     # film
    "Q202866",    # animated film
    "Q24869",     # feature film
    "Q506240",    # television film
}


def resolve_ids_via_wikidata(
    *,
    imdb_id: str | None = None,
    wikidata_id: str | None = None,
    kp_id: int | None = None,
) -> dict[str, Any]:
    """По wikidata_id, imdb_id (P345) или kp_id (P2603) получает kp_id, imdb_id и rt_slug (P1258) через официальный Wikidata API."""
    if not imdb_id and not wikidata_id and not kp_id:
        return {}

    qids: list[str] = []
    if wikidata_id and str(wikidata_id).startswith("Q"):
        qids.append(str(wikidata_id))

    try:
        with httpx.Client(timeout=10.0, headers={"User-Agent": WIKIDATA_USER_AGENT}) as client:
            if imdb_id:
                safe_imdb = str(imdb_id).strip()
                s_resp = client.get(
                    WIKIDATA_API_URL,
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": f"haswbstatement:P345={safe_imdb}",
                        "format": "json",
                    },
                )
                if s_resp.status_code == 200:
                    for hit in (s_resp.json().get("query") or {}).get("search") or []:
                        title = hit.get("title")
                        if title and title.startswith("Q") and title not in qids:
                            qids.append(title)

            if kp_id and not qids:
                s_resp = client.get(
                    WIKIDATA_API_URL,
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": f"haswbstatement:P2603={int(kp_id)}",
                        "format": "json",
                    },
                )
                if s_resp.status_code == 200:
                    for hit in (s_resp.json().get("query") or {}).get("search") or []:
                        title = hit.get("title")
                        if title and title.startswith("Q") and title not in qids:
                            qids.append(title)

            if not qids:
                return {}

            ent_resp = client.get(
                WIKIDATA_API_URL,
                params={
                    "action": "wbgetentities",
                    "ids": "|".join(qids[:5]),
                    "props": "claims",
                    "format": "json",
                },
            )
            ent_resp.raise_for_status()
            entities = ent_resp.json().get("entities") or {}

            resolved_imdb = imdb_id
            resolved_kp = kp_id
            resolved_url_rt: str | None = None
            resolved_qid = qids[0]

            for qid in qids:
                claims = (entities.get(qid) or {}).get("claims") or {}
                if not resolved_imdb:
                    imdb_vals = _extract_claim_values(claims, "P345")
                    resolved_imdb = next((str(v) for v in imdb_vals if str(v).startswith("tt")), None)
                if not resolved_kp:
                    kp_vals = _extract_claim_values(claims, "P2603")
                    resolved_kp = next((int(v) for v in kp_vals if str(v).isdigit()), None)
                if not resolved_url_rt:
                    rt_vals = _extract_claim_values(claims, "P1258")
                    if rt_vals:
                        rt_slug = str(rt_vals[0]).lstrip("/")
                        resolved_url_rt = f"https://www.rottentomatoes.com/{rt_slug}"

            return {
                "wikidata_id": resolved_qid,
                "imdb_id": resolved_imdb,
                "kp_id": resolved_kp,
                "url_rt": resolved_url_rt,
            }
    except Exception:
        return {}


def fetch_imdb_rating(imdb_id: str | None) -> float | None:
    """Резервное получение рейтинга IMDb напрямую по tt-ID, если его нет в XML Кинопоиска."""
    if not imdb_id or not str(imdb_id).startswith("tt"):
        return None
    query = f'query {{ title(id: "{imdb_id}") {{ ratingsSummary {{ aggregateRating }} }} }}'
    try:
        with httpx.Client(
            timeout=8.0,
            headers={
                "Content-Type": "application/json",
                "x-imdb-client-name": "imdb-web-next-localized",
                "User-Agent": USER_AGENT,
            },
        ) as client:
            resp = client.post("https://caching.graphql.imdb.com/", json={"query": query})
            if resp.status_code != 200:
                return None
            val = (((resp.json().get("data") or {}).get("title") or {}).get("ratingsSummary") or {}).get("aggregateRating")
            return round(float(val), 1) if val is not None and float(val) > 0 else None
    except Exception:
        return None


def fetch_kp_and_imdb_ratings(kp_id: int | None) -> dict[str, float | None]:
    """Получает официальный XML рейтингов с https://rating.kinopoisk.ru/{kp_id}.xml (без ключей)."""
    if not kp_id:
        return {"rating_kp": None, "rating_imdb": None}

    url = f"https://rating.kinopoisk.ru/{kp_id}.xml"
    try:
        with httpx.Client(timeout=8.0, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(url)
            if resp.status_code != 200 or not resp.text.strip().startswith("<"):
                return {"rating_kp": None, "rating_imdb": None}
            root = ET.fromstring(resp.text)
            kp_node = root.find("kp_rating")
            imdb_node = root.find("imdb_rating")
            rating_kp = round(float(kp_node.text), 1) if kp_node is not None and kp_node.text else None
            rating_imdb = round(float(imdb_node.text), 1) if imdb_node is not None and imdb_node.text else None
            if rating_kp == 0.0:
                rating_kp = None
            if rating_imdb == 0.0:
                rating_imdb = None
            return {"rating_kp": rating_kp, "rating_imdb": rating_imdb}
    except Exception:
        return {"rating_kp": None, "rating_imdb": None}


def build_fallback_rt_url(title_orig: str | None, title_ru: str | None) -> str | None:
    query = (title_orig or title_ru or "").strip()
    if not query:
        return None
    return f"https://www.rottentomatoes.com/search?search={quote_plus(query)}"


def build_fallback_kp_url(title_ru: str | None, title_orig: str | None) -> str | None:
    query = (title_ru or title_orig or "").strip()
    if not query:
        return None
    return f"https://www.kinopoisk.ru/index.php?kp_query={quote_plus(query)}"


def guess_and_fetch_rt(
    title_orig: str | None,
    release_year: int | None = None,
    category: str = "movie",
) -> tuple[str | None, int | None]:
    """Пробует угадать прямую страницу фильма/сериала на Rotten Tomatoes по оригинальному названию, если P1258 нет в Wikidata."""
    if not title_orig:
        return None, None
    slug = re.sub(r"[^a-z0-9]+", "_", title_orig.lower()).strip("_")
    if not slug:
        return None, None
    prefix = "tv" if category == "series" else "m"
    candidates = [f"https://www.rottentomatoes.com/{prefix}/{slug}"]
    if release_year and prefix == "m":
        candidates.insert(0, f"https://www.rottentomatoes.com/{prefix}/{slug}_{release_year}")
    for candidate_url in candidates:
        score = fetch_rt_score(candidate_url)
        if score is not None:
            return candidate_url, score
    return None, None


def fetch_rt_score(url_rt: str | None) -> int | None:
    """Извлекает процент Tomatometer с прямой страницы фильма/сериала на Rotten Tomatoes (без ключей)."""
    if not url_rt or "/search?" in url_rt:
        return None
    try:
        with httpx.Client(timeout=8.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(url_rt)
            if resp.status_code != 200:
                return None
            m = _RT_SCORE_RE.search(resp.text)
            if not m:
                return None
            raw_val = m.group(1) or m.group(2)
            score = int(raw_val) if raw_val and raw_val.isdigit() else None
            return score if score is not None and 0 <= score <= 100 else None
    except Exception:
        return None


def _extract_claim_values(claims: dict[str, Any], prop: str) -> list[Any]:
    out: list[Any] = []
    for statement in claims.get(prop, []):
        datavalue = (statement.get("mainsnak") or {}).get("datavalue") or {}
        val = datavalue.get("value")
        if val is not None:
            out.append(val)
    return out


def search_wikidata_movies(query: str, year: int | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """Резервный официальный поиск фильмов и сериалов через Wikidata API (поддерживает и русский, и английский запрос)."""
    is_ascii = all(ord(ch) < 128 for ch in query)
    langs_to_try = ["en", "ru"] if is_ascii else ["ru", "en"]

    try:
        with httpx.Client(timeout=12.0, headers={"User-Agent": WIKIDATA_USER_AGENT}) as client:
            qids: list[str] = []
            for search_lang in langs_to_try:
                search_resp = client.get(
                    WIKIDATA_API_URL,
                    params={
                        "action": "wbsearchentities",
                        "search": query,
                        "language": search_lang,
                        "uselang": "ru",
                        "limit": 10,
                        "format": "json",
                    },
                )
                search_resp.raise_for_status()
                for h in search_resp.json().get("search") or []:
                    if h.get("id") and h["id"] not in qids:
                        qids.append(h["id"])
                if len(qids) >= 8:
                    break

            if not qids:
                return []

            ent_resp = client.get(
                WIKIDATA_API_URL,
                params={
                    "action": "wbgetentities",
                    "ids": "|".join(qids[:12]),
                    "languages": "ru|en",
                    "props": "labels|descriptions|claims",
                    "format": "json",
                },
            )
            ent_resp.raise_for_status()
            entities = ent_resp.json().get("entities") or {}
    except Exception:
        return []

    results: list[dict[str, Any]] = []
    for qid in qids:
        ent = entities.get(qid) or {}
        claims = ent.get("claims") or {}

        imdb_vals = _extract_claim_values(claims, "P345")
        kp_vals = _extract_claim_values(claims, "P2603")
        p31_ids = {v.get("id") for v in _extract_claim_values(claims, "P31") if isinstance(v, dict)}

        is_series = bool(p31_ids & _SERIES_QIDS)
        is_movie = bool(p31_ids & _MOVIE_QIDS)
        # Принимаем сущность, если у неё есть IMDb tt-ID / Кинопоиск ID или тип фильма/сериала
        imdb_id = next((str(v) for v in imdb_vals if str(v).startswith("tt")), None)
        kp_id = next((int(v) for v in kp_vals if str(v).isdigit()), None)
        if not (imdb_id or kp_id or is_series or is_movie):
            continue

        # Год выхода (P577 — publication date или P580 — start time)
        release_year: int | None = None
        for date_prop in ("P577", "P580"):
            for date_val in _extract_claim_values(claims, date_prop):
                if isinstance(date_val, dict) and date_val.get("time"):
                    raw_time = str(date_val["time"]).lstrip("+")
                    if len(raw_time) >= 4 and raw_time[:4].isdigit():
                        release_year = int(raw_time[:4])
                        break
            if release_year:
                break

        if year and release_year and abs(release_year - year) > 1:
            continue

        labels = ent.get("labels") or {}
        descs = ent.get("descriptions") or {}
        title_ru = (labels.get("ru") or {}).get("value") or (labels.get("en") or {}).get("value") or query
        title_orig = (labels.get("en") or {}).get("value")
        desc_ru = (descs.get("ru") or {}).get("value") or (descs.get("en") or {}).get("value")

        rt_vals = _extract_claim_values(claims, "P1258")
        rt_slug = str(rt_vals[0]) if rt_vals else None

        category = "series" if is_series and not is_movie else "movie"
        results.append(
            {
                "source": "wikidata",
                "wikidata_id": qid,
                "category": category,
                "title_ru": title_ru,
                "title_orig": title_orig if title_orig != title_ru else None,
                "release_year": release_year,
                "summary": desc_ru,
                "imdb_id": imdb_id,
                "kp_id": kp_id,
                "url_rt": f"https://www.rottentomatoes.com/{rt_slug.lstrip('/')}" if rt_slug else None,
            }
        )
        if len(results) >= limit:
            break
    return results
