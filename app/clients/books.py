from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings

GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
OPENLIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
RU_WIKI_API_URL = "https://ru.wikipedia.org/w/api.php"
WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
FANTLAB_SEARCH_URL = "https://api.fantlab.ru/search-works.json"
FANTLAB_WORK_URL = "https://api.fantlab.ru/work"
GOODREADS_SEARCH_URL = "https://www.goodreads.com/search"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PersonalSecondBrainBot/0.4"

_YEAR_RE = re.compile(r"((?:18|19|20)\d{2})")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_DOUBLED_LETTERS_RE = re.compile(r"(.)\1+", flags=re.UNICODE)
_GR_BOOK_PATH_RE = re.compile(r'href=["\'](/book/show/\d+[^"\'?#]*)')
_GR_RATING_RE = re.compile(r"([0-9]\.[0-9]{2})\s+avg\s+rating", flags=re.IGNORECASE)

# P31 Q-IDs для книг / литературных произведений в Wikidata
_BOOK_QIDS = {
    "Q571",       # book
    "Q7725634",   # literary work
    "Q8261",      # novel
    "Q47461344",  # written work
    "Q1667921",   # novel series
    "Q277759",    # book series
}


def _extract_year(raw: str | None) -> int | None:
    if not raw:
        return None
    m = _YEAR_RE.search(str(raw))
    return int(m.group(1)) if m else None


def _strip_html(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = _HTML_TAG_RE.sub("", text).strip()
    return cleaned or None


def _query_variants(query: str) -> list[str]:
    """Возвращает исходный запрос и вариант со схлопнутыми удвоенными буквами ('гипперион' -> 'гиперион')."""
    q = query.strip()
    deduped = _DOUBLED_LETTERS_RE.sub(r"\1", q)
    if deduped.lower() != q.lower():
        return [q, deduped]
    return [q]


class BooksClient:
    """Клиент официальных Google Books API + Wikipedia/Wikidata (с исправлением опечаток) + OpenLibrary API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (api_key if api_key is not None else settings.google_books_api_key).strip()

    def search_google_books(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        params: dict[str, Any] = {
            "q": query,
            "maxResults": min(limit * 2, 10),
            "printType": "books",
            "langRestrict": "ru",
            "key": self.api_key,
        }
        try:
            with httpx.Client(timeout=12.0, headers={"User-Agent": USER_AGENT}) as client:
                resp = client.get(GOOGLE_BOOKS_URL, params=params)
                items = (resp.json().get("items") or []) if resp.status_code == 200 else []
                if not items:
                    # Повтор без langRestrict для редких или англоязычных книг
                    params.pop("langRestrict", None)
                    resp = client.get(GOOGLE_BOOKS_URL, params=params)
                    items = (resp.json().get("items") or []) if resp.status_code == 200 else []
        except Exception:
            return []

        results: list[dict[str, Any]] = []
        for raw in items:
            vol_id = raw.get("id")
            info = raw.get("volumeInfo") or {}
            title = (info.get("title") or "").strip()
            if not title:
                continue

            authors = [a.strip() for a in (info.get("authors") or []) if a.strip()]
            creator = ", ".join(authors[:3]) if authors else None
            release_year = _extract_year(info.get("publishedDate"))
            summary = _strip_html(info.get("description"))

            isbn13: str | None = None
            for ident in info.get("industryIdentifiers") or []:
                if ident.get("type") == "ISBN_13" and ident.get("identifier"):
                    isbn13 = str(ident["identifier"])
                    break
            if not isbn13:
                for ident in info.get("industryIdentifiers") or []:
                    if ident.get("identifier"):
                        isbn13 = str(ident["identifier"])
                        break

            img_links = info.get("imageLinks") or {}
            poster_url = img_links.get("thumbnail") or img_links.get("smallThumbnail")
            if poster_url and poster_url.startswith("http://"):
                poster_url = "https://" + poster_url[len("http://") :]

            categories = [c.strip().lower() for c in (info.get("categories") or []) if c.strip()]
            page_count = info.get("pageCount")
            info_link = info.get("infoLink") or (
                f"https://books.google.com/books?id={vol_id}" if vol_id else None
            )

            results.append(
                {
                    "source": "google_books",
                    "category": "book",
                    "google_books_id": vol_id,
                    "title_ru": title,
                    "title_orig": None,
                    "creator": creator,
                    "release_year": release_year,
                    "summary": summary,
                    "poster_url": poster_url,
                    "isbn13": isbn13,
                    "genres": categories,
                    "page_count": page_count,
                    "info_link": info_link,
                }
            )
            if len(results) >= limit:
                break
        return results

    def search_wikipedia_books(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """Ищет книги через официальный API русской Википедии + Wikidata (понимает опечатки, например 'гипперион')."""
        try:
            with httpx.Client(timeout=12.0, headers={"User-Agent": USER_AGENT}) as client:
                page_ids: list[int] = []
                for variant in _query_variants(query):
                    for suffix in (" роман книга", ""):
                        s_resp = client.get(
                            RU_WIKI_API_URL,
                            params={
                                "action": "query",
                                "list": "search",
                                "srsearch": f"{variant}{suffix}",
                                "srlimit": 6,
                                "format": "json",
                            },
                        )
                        s_resp.raise_for_status()
                        s_data = s_resp.json().get("query") or {}
                        for hit in s_data.get("search") or []:
                            pid = hit.get("pageid")
                            if pid and pid not in page_ids:
                                page_ids.append(int(pid))
                        if len(page_ids) >= 6:
                            break
                    if len(page_ids) >= 6:
                        break

                if not page_ids:
                    return []

                p_resp = client.get(
                    RU_WIKI_API_URL,
                    params={
                        "action": "query",
                        "pageids": "|".join(str(p) for p in page_ids[:8]),
                        "prop": "pageprops|extracts|pageimages",
                        "exintro": 1,
                        "explaintext": 1,
                        "piprop": "original",
                        "format": "json",
                    },
                )
                p_resp.raise_for_status()
                pages = (p_resp.json().get("query") or {}).get("pages") or {}

                qids = [
                    (pages.get(str(pid), {}).get("pageprops") or {}).get("wikibase_item")
                    for pid in page_ids[:8]
                ]
                valid_qids = [q for q in qids if q]
                if not valid_qids:
                    return []

                wd_resp = client.get(
                    WIKIDATA_API_URL,
                    params={
                        "action": "wbgetentities",
                        "ids": "|".join(valid_qids),
                        "languages": "ru|en",
                        "props": "labels|descriptions|claims",
                        "format": "json",
                    },
                )
                wd_resp.raise_for_status()
                entities = wd_resp.json().get("entities") or {}

                # Собираем Q-ID авторов (P50), чтобы получить их имена на русском
                author_qids: set[str] = set()
                for qid in valid_qids:
                    claims = (entities.get(qid) or {}).get("claims") or {}
                    for st in claims.get("P50", []):
                        val = ((st.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                        if isinstance(val, dict) and val.get("id"):
                            author_qids.add(str(val["id"]))

                author_names: dict[str, str] = {}
                if author_qids:
                    a_resp = client.get(
                        WIKIDATA_API_URL,
                        params={
                            "action": "wbgetentities",
                            "ids": "|".join(list(author_qids)[:20]),
                            "languages": "ru|en",
                            "props": "labels",
                            "format": "json",
                        },
                    )
                    if a_resp.status_code == 200:
                        for a_id, a_ent in (a_resp.json().get("entities") or {}).items():
                            lbls = a_ent.get("labels") or {}
                            name = (lbls.get("ru") or {}).get("value") or (lbls.get("en") or {}).get("value")
                            if name:
                                author_names[a_id] = name
        except Exception:
            return []

        results: list[dict[str, Any]] = []
        for pid in page_ids[:8]:
            page = pages.get(str(pid)) or {}
            qid = (page.get("pageprops") or {}).get("wikibase_item")
            if not qid or qid not in entities:
                continue

            ent = entities[qid]
            claims = ent.get("claims") or {}
            p31_ids = {
                ((st.get("mainsnak") or {}).get("datavalue") or {}).get("value", {}).get("id")
                for st in claims.get("P31", [])
                if isinstance(((st.get("mainsnak") or {}).get("datavalue") or {}).get("value"), dict)
            }
            has_author = bool(claims.get("P50"))
            if not (p31_ids & _BOOK_QIDS) and not has_author:
                continue

            labels = ent.get("labels") or {}
            raw_title = (labels.get("ru") or {}).get("value") or page.get("title") or query
            # Убираем уточнение '(роман)' / '(книга)' в скобках
            clean_title = re.sub(r"\s*\((?:роман|книга|повесть|рассказ|цикл).*?\)\s*$", "", str(raw_title), flags=re.I)
            title_orig = (labels.get("en") or {}).get("value")

            authors: list[str] = []
            for st in claims.get("P50", []):
                val = ((st.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                if isinstance(val, dict) and val.get("id") in author_names:
                    authors.append(author_names[str(val["id"])])
            creator = ", ".join(authors[:3]) if authors else None

            release_year: int | None = None
            for st in claims.get("P577", []):
                val = ((st.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                if isinstance(val, dict) and val.get("time"):
                    t_str = str(val["time"]).lstrip("+")
                    if len(t_str) >= 4 and t_str[:4].isdigit():
                        release_year = int(t_str[:4])
                        break

            extract = (page.get("extract") or "").strip()
            poster_url = (page.get("original") or {}).get("source")
            wiki_title = page.get("title") or clean_title
            info_link = f"https://ru.wikipedia.org/wiki/{quote(str(wiki_title).replace(' ', '_'))}"

            results.append(
                {
                    "source": "wikipedia",
                    "category": "book",
                    "google_books_id": f"wd:{qid}",
                    "title_ru": clean_title,
                    "title_orig": title_orig if title_orig != clean_title else None,
                    "creator": creator,
                    "release_year": release_year,
                    "summary": extract or None,
                    "poster_url": poster_url,
                    "isbn13": None,
                    "genres": [],
                    "page_count": None,
                    "info_link": info_link,
                }
            )
            if len(results) >= limit:
                break
        return results

    def search_openlibrary(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        for variant in _query_variants(query):
            try:
                with httpx.Client(timeout=12.0, headers={"User-Agent": USER_AGENT}) as client:
                    resp = client.get(OPENLIBRARY_SEARCH_URL, params={"q": variant, "limit": limit})
                    resp.raise_for_status()
                    docs = resp.json().get("docs") or []
            except Exception:
                continue

            results: list[dict[str, Any]] = []
            for doc in docs[:limit]:
                title = (doc.get("title") or "").strip()
                if not title:
                    continue
                authors = [a.strip() for a in (doc.get("author_name") or []) if a.strip()]
                creator = ", ".join(authors[:3]) if authors else None
                release_year = doc.get("first_publish_year")
                cover_i = doc.get("cover_i")
                poster_url = f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg" if cover_i else None
                work_key = doc.get("key")
                isbns = doc.get("isbn") or []
                isbn13 = next((str(i) for i in isbns if len(str(i)) == 13), str(isbns[0]) if isbns else None)

                results.append(
                    {
                        "source": "openlibrary",
                        "category": "book",
                        "google_books_id": f"ol:{work_key}" if work_key else None,
                        "title_ru": title,
                        "title_orig": None,
                        "creator": creator,
                        "release_year": int(release_year) if release_year else None,
                        "summary": None,
                        "poster_url": poster_url,
                        "isbn13": isbn13,
                        "genres": [],
                        "page_count": doc.get("number_of_pages_median"),
                        "info_link": f"https://openlibrary.org{work_key}" if work_key else None,
                    }
                )
            if results:
                return results
        return []

    def search_candidates(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        if self.api_key:
            for variant in _query_variants(query):
                candidates = self.search_google_books(variant, limit=limit)
                if candidates:
                    return candidates

        wiki_candidates = self.search_wikipedia_books(query, limit=limit)
        if wiki_candidates:
            return wiki_candidates

        fl_candidates = self.search_fantlab_books(query, limit=limit)
        if fl_candidates:
            return fl_candidates

        return self.search_openlibrary(query, limit=limit)

    def search_fantlab_books(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """Ищет книги через официальный JSON API FantLab (api.fantlab.ru)."""
        for variant in _query_variants(query):
            try:
                with httpx.Client(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
                    resp = client.get(FANTLAB_SEARCH_URL, params={"q": variant})
                    if resp.status_code != 200:
                        continue
                    matches = (resp.json() or {}).get("matches") or []
            except Exception:
                continue

            results: list[dict[str, Any]] = []
            for m in matches:
                work_id = m.get("work_id")
                title_ru = (m.get("rusname") or m.get("name") or "").strip()
                if not work_id or not title_ru:
                    continue
                title_orig = (m.get("name") or "").strip() or None
                creator = (m.get("all_autor_rusname") or m.get("all_autor_name") or "").strip() or None
                year = int(m["year"]) if m.get("year") and str(m["year"]).isdigit() else None
                raw_rating = (m.get("rating") or [None])[0]
                rating_fl = round(float(raw_rating), 2) if raw_rating else None
                pic_id = m.get("pic_edition_id") or m.get("pic_edition_id_auto")
                poster_url = f"https://fantlab.ru/images/editions/big/{pic_id}" if pic_id else None

                results.append(
                    {
                        "source": "fantlab",
                        "category": "book",
                        "google_books_id": f"fl:{work_id}",
                        "title_ru": title_ru,
                        "title_orig": title_orig if title_orig != title_ru else None,
                        "creator": creator,
                        "release_year": year,
                        "summary": None,
                        "poster_url": poster_url,
                        "isbn13": None,
                        "genres": [],
                        "rating_fantlab": rating_fl,
                        "url_fantlab": f"https://fantlab.ru/work{work_id}",
                    }
                )
                if len(results) >= limit:
                    break
            if results:
                return results
        return []


def fetch_fantlab_info(title_ru: str | None, creator: str | None = None) -> dict[str, Any]:
    """Находит книгу на FantLab и возвращает {'rating_fantlab', 'url_fantlab', 'summary'}."""
    if not title_ru:
        return {}
    queries = [f"{creator} {title_ru}".strip()] if creator else []
    queries.append(title_ru)

    for q in queries:
        for variant in _query_variants(q):
            try:
                with httpx.Client(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
                    resp = client.get(FANTLAB_SEARCH_URL, params={"q": variant})
                    if resp.status_code != 200:
                        continue
                    matches = (resp.json() or {}).get("matches") or []
                    if not matches:
                        continue
                    top = matches[0]
                    work_id = top.get("work_id")
                    raw_r = (top.get("rating") or [None])[0]
                    rating_fl = round(float(raw_r), 2) if raw_r and float(raw_r) > 0 else None
                    url_fl = f"https://fantlab.ru/work{work_id}" if work_id else None

                    summary: str | None = None
                    genres: list[str] = []
                    if top.get("name_show_im"):
                        genres.append(str(top["name_show_im"]).strip().lower())
                    if work_id:
                        w_resp = client.get(f"{FANTLAB_WORK_URL}/{work_id}")
                        if w_resp.status_code == 200:
                            w_data = w_resp.json() or {}
                            summary = _strip_html(w_data.get("work_description"))
                    return {
                        "fantlab_id": int(work_id) if work_id else None,
                        "rating_fantlab": rating_fl,
                        "url_fantlab": url_fl,
                        "summary": summary,
                        "genres": genres,
                    }
            except Exception:
                continue
    return {}


def fetch_goodreads_info(title_orig: str | None, title_ru: str | None, creator: str | None = None) -> dict[str, Any]:
    """Находит книгу на Goodreads и возвращает {'rating_goodreads', 'url_goodreads'}."""
    base_title = (title_orig or title_ru or "").strip()
    if not base_title:
        return {}
    q = f"{base_title} {creator}".strip() if creator and not title_orig else base_title
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(GOODREADS_SEARCH_URL, params={"q": q})
            if resp.status_code != 200:
                return {}
            text = resp.text
            m_path = _GR_BOOK_PATH_RE.search(text)
            m_rate = _GR_RATING_RE.search(text)
            url_gr = f"https://www.goodreads.com{m_path.group(1)}" if m_path else None
            rating_gr = round(float(m_rate.group(1)), 2) if m_rate else None
            return {"rating_goodreads": rating_gr, "url_goodreads": url_gr}
    except Exception:
        return {}
