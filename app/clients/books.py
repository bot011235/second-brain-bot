from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings
from app.utils.normalize import normalize_text

GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
OPENLIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
RU_WIKI_API_URL = "https://ru.wikipedia.org/w/api.php"
WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
FANTLAB_SEARCH_URL = "https://api.fantlab.ru/search-works.json"
FANTLAB_WORK_URL = "https://api.fantlab.ru/work"
GOODREADS_SEARCH_URL = "https://www.goodreads.com/search"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PersonalSecondBrainBot/0.4"
WIKI_USER_AGENT = "PersonalSecondBrainBot/1.0 (https://github.com/bot011235/second-brain-bot)"
_HTTP_TIMEOUT = httpx.Timeout(6.0, connect=4.0)

_YEAR_RE = re.compile(r"((?:18|19|20)\d{2})")
_LIST_ITEM_PREFIX_RE = re.compile(r"^\s*(?:\d+[\.\)\-:]|[-•*—–])\s*")
_TRAILING_BOOK_YEAR_RE = re.compile(r"(?:\s*[,\(\[]?\s*((?:18|19|20)\d{2})\s*[\)\]]?\s*)$")
_DASH_AUTHOR_SPLIT_RE = re.compile(r"\s+[—–-]\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_DOUBLED_LETTERS_RE = re.compile(r"(.)\1+", flags=re.UNICODE)
_CYRILLIC_RE = re.compile(r"[а-яА-ЯёЁ]")
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


def parse_book_query(raw_query: str) -> tuple[str, str | None, int | None]:
    """Разбирает строку книги: '1. Американский психопат — Брет Истон Эллис (1991)' -> ('Американский психопат', 'Брет Истон Эллис', 1991)."""
    text = (raw_query or "").strip()
    text = _LIST_ITEM_PREFIX_RE.sub("", text).strip()

    year: int | None = None
    m_year = _TRAILING_BOOK_YEAR_RE.search(text)
    if m_year:
        prefix = text[: m_year.start()].strip()
        if prefix:
            year = int(m_year.group(1))
            text = prefix

    author: str | None = None
    parts = _DASH_AUTHOR_SPLIT_RE.split(text, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        title = parts[0].strip()
        author = parts[1].strip()
    else:
        title = text

    return title, author, year


def _author_similarity(query_author: str | None, cand_creator: str | None) -> float:
    norm_qa = normalize_text(query_author, strip_articles=False)
    norm_cc = normalize_text(cand_creator, strip_articles=False)
    if not norm_qa or not norm_cc:
        return 0.0
    if norm_qa == norm_cc or norm_qa in norm_cc or norm_cc in norm_qa:
        return 1.0

    q_tokens = [t for t in norm_qa.split() if len(t) >= 2]
    c_tokens = [t for t in norm_cc.split() if len(t) >= 2]
    if not q_tokens or not c_tokens:
        return SequenceMatcher(None, norm_qa, norm_cc).ratio()

    best_surname = SequenceMatcher(None, q_tokens[-1], c_tokens[-1]).ratio()
    best_pair = max(
        (SequenceMatcher(None, qt, ct).ratio() for qt in q_tokens for ct in c_tokens),
        default=0.0,
    )
    overlap = len(set(q_tokens) & set(c_tokens)) / max(1, min(len(q_tokens), len(c_tokens)))
    return max(SequenceMatcher(None, norm_qa, norm_cc).ratio(), best_surname, best_pair * 0.92, overlap)


def _title_similarity(query_title: str, candidate: dict[str, Any]) -> float:
    norm_q = normalize_text(query_title, strip_articles=False)
    if not norm_q:
        return 0.0
    cand_titles: list[str] = []
    for key in ("title_ru", "title_orig", "alt_title"):
        val = candidate.get(key)
        if isinstance(val, str) and val.strip():
            cand_titles.append(val)

    best = 0.0
    q_tokens = set(norm_q.split())
    for raw_t in cand_titles:
        norm_t = normalize_text(raw_t, strip_articles=False)
        if not norm_t:
            continue
        if norm_t == norm_q:
            return 1.0
        if (len(norm_q) >= 4 and (norm_q in norm_t or norm_t in norm_q)) or (len(norm_t) >= 2 and norm_t in q_tokens):
            score = 0.85
        else:
            t_tokens = set(norm_t.split())
            tok_overlap = len(q_tokens & t_tokens) / max(1, min(len(q_tokens), len(t_tokens)))
            seq = SequenceMatcher(None, norm_q, norm_t).ratio()
            score = max(seq, tok_overlap * 0.8)
        if score > best:
            best = score
    return best


def _score_book_candidate(
    candidate: dict[str, Any],
    title: str,
    author: str | None = None,
    year: int | None = None,
) -> float:
    t_sim = _title_similarity(title, candidate)
    if t_sim >= 0.99:
        score = 6.0
    elif t_sim >= 0.82:
        score = 4.2
    else:
        score = t_sim * 4.5

    if author:
        creator = candidate.get("creator")
        if creator:
            a_sim = _author_similarity(author, creator)
            if a_sim >= 0.85:
                score += 4.5
            elif a_sim >= 0.70:
                score += 3.0
            elif a_sim >= 0.50:
                score += 0.8
            else:
                score -= 3.5
        else:
            score -= 0.5

    cand_year = candidate.get("release_year")
    if year and cand_year:
        try:
            diff = abs(int(cand_year) - int(year))
            if diff == 0:
                score += 3.0
            elif diff <= 1:
                score += 1.5
            elif diff > 5:
                score -= 0.8
        except (TypeError, ValueError):
            pass

    if candidate.get("poster_url"):
        score += 0.3
    if candidate.get("rating_fantlab"):
        score += 0.4
    return score


def _is_relevant_book_candidate(
    candidate: dict[str, Any],
    title: str,
    author: str | None = None,
    year: int | None = None,
) -> bool:
    t_sim = _title_similarity(title, candidate)
    creator = candidate.get("creator")
    a_sim = _author_similarity(author, creator) if (author and creator) else None

    if t_sim >= 0.55 and (a_sim is None or a_sim >= 0.52):
        return True

    if author and a_sim is not None and a_sim >= 0.72:
        cand_year = candidate.get("release_year")
        if year and cand_year:
            try:
                if abs(int(cand_year) - int(year)) <= 2:
                    return True
            except (TypeError, ValueError):
                pass
        if t_sim >= 0.45:
            return True

    return False


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
            with httpx.Client(timeout=_HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
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
            with httpx.Client(timeout=_HTTP_TIMEOUT, headers={"User-Agent": WIKI_USER_AGENT}) as client:
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
                with httpx.Client(timeout=_HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
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

    def _raw_search_fantlab(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        for variant in _query_variants(query):
            try:
                with httpx.Client(timeout=_HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
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
                raw_name = (m.get("name") or "").strip() or None
                title_orig = (
                    raw_name
                    if raw_name and raw_name != title_ru
                    else (m.get("name_eng") or "").strip() or None
                )
                alt_title = (m.get("altname") or "").strip() or None
                creator = (m.get("all_autor_rusname") or m.get("all_autor_name") or "").strip() or None
                year = int(m["year"]) if m.get("year") and str(m["year"]).isdigit() else None
                raw_rating = (m.get("rating") or [None])[0]
                try:
                    rating_fl = round(float(raw_rating), 2) if raw_rating and float(raw_rating) > 0 else None
                except (TypeError, ValueError):
                    rating_fl = None
                pic_id = m.get("pic_edition_id") or m.get("pic_edition_id_auto")
                poster_url = f"https://fantlab.ru/images/editions/big/{pic_id}" if pic_id else None

                cand: dict[str, Any] = {
                    "source": "fantlab",
                    "category": "book",
                    "fantlab_id": int(work_id),
                    "google_books_id": f"fl:{work_id}",
                    "title_ru": title_ru,
                    "title_orig": title_orig,
                    "creator": creator,
                    "release_year": year,
                    "summary": None,
                    "poster_url": poster_url,
                    "isbn13": None,
                    "genres": [],
                    "rating_fantlab": rating_fl,
                    "url_fantlab": f"https://fantlab.ru/work{work_id}",
                }
                if alt_title and alt_title != title_ru:
                    cand["alt_title"] = alt_title
                results.append(cand)
                if len(results) >= max_results:
                    break
            if results:
                return results
        return []

    def _search_fantlab_ranked(
        self, title: str, author: str | None, year: int | None, limit: int = 3
    ) -> list[dict[str, Any]]:
        clean_q = f"{title} {author}".strip() if author else title
        pool: list[dict[str, Any]] = self._raw_search_fantlab(clean_q, max_results=10)
        best_score = max(
            (_score_book_candidate(c, title, author, year) for c in pool),
            default=0.0,
        )
        if author and (not pool or best_score < 5.0):
            title_hits = self._raw_search_fantlab(title, max_results=10)
            seen_ids = {c.get("fantlab_id") or c.get("google_books_id") for c in pool}
            for c in title_hits:
                key = c.get("fantlab_id") or c.get("google_books_id")
                if key not in seen_ids:
                    seen_ids.add(key)
                    pool.append(c)

        filtered = [c for c in pool if _is_relevant_book_candidate(c, title, author, year)]
        if not filtered and not author:
            # Без автора принимаем непустые совпадения по токенам (например запрос 'Хайдеггер Бытие')
            norm_q = normalize_text(title, strip_articles=False)
            filtered = [
                c
                for c in pool
                if any(
                    tok in norm_q
                    for tok in normalize_text(f"{c.get('title_ru', '')} {c.get('creator', '')}", strip_articles=False).split()
                    if len(tok) >= 3
                )
            ]
        filtered.sort(key=lambda c: _score_book_candidate(c, title, author, year), reverse=True)
        for c in filtered:
            c.pop("alt_title", None)
        return filtered[:limit]

    def _filter_and_rank(
        self, candidates: list[dict[str, Any]], title: str, author: str | None, year: int | None, limit: int
    ) -> list[dict[str, Any]]:
        filtered = [c for c in candidates if _is_relevant_book_candidate(c, title, author, year)]
        filtered.sort(key=lambda c: _score_book_candidate(c, title, author, year), reverse=True)
        return filtered[:limit]

    def search_candidates(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        title, author, year = parse_book_query(query)
        clean_q = f"{title} {author}".strip() if author else (title or query.strip())
        is_cyrillic = bool(_CYRILLIC_RE.search(clean_q))

        def _try_google() -> list[dict[str, Any]]:
            if not self.api_key:
                return []
            for q_str in dict.fromkeys([clean_q, title] if author else [clean_q]):
                for variant in _query_variants(q_str):
                    raw = self.search_google_books(variant, limit=max(limit, 5))
                    ranked = self._filter_and_rank(raw, title, author, year, limit)
                    if ranked:
                        return ranked
            return []

        def _try_wiki() -> list[dict[str, Any]]:
            for q_str in dict.fromkeys([clean_q, title] if author else [clean_q]):
                raw = self.search_wikipedia_books(q_str, limit=max(limit, 4))
                ranked = self._filter_and_rank(raw, title, author, year, limit)
                if ranked:
                    return ranked
            return []

        def _try_fantlab() -> list[dict[str, Any]]:
            return self._search_fantlab_ranked(title, author, year, limit=limit)

        def _try_openlibrary() -> list[dict[str, Any]]:
            raw = self.search_openlibrary(clean_q, limit=max(limit, 4))
            return self._filter_and_rank(raw, title, author, year, limit)

        providers = (
            (_try_fantlab, _try_wiki, _try_google, _try_openlibrary)
            if is_cyrillic
            else (_try_google, _try_fantlab, _try_openlibrary, _try_wiki)
        )
        for fn in providers:
            hits = fn()
            if hits:
                return hits
        return []

    def search_fantlab_books(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """Ищет книги через официальный JSON API FantLab (api.fantlab.ru)."""
        raw = self._raw_search_fantlab(query, max_results=max(limit, 10))
        title, author, year = parse_book_query(query)
        raw.sort(key=lambda c: _score_book_candidate(c, title, author, year), reverse=True)
        for c in raw:
            c.pop("alt_title", None)
        return raw[:limit]


def _extract_fantlab_genres(w_data: dict[str, Any]) -> list[str]:
    genres: list[str] = []
    classificatory = w_data.get("classificatory")
    if isinstance(classificatory, dict):
        for grp in classificatory.get("genre_group") or []:
            if grp.get("genre_group_id") != 1:
                continue

            def _walk(nodes: Any) -> None:
                if not isinstance(nodes, list):
                    return
                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    lbl = str(node.get("label") or "").strip().lower()
                    if lbl and lbl not in genres:
                        genres.append(lbl)
                    if node.get("genre"):
                        _walk(node["genre"])

            _walk(grp.get("genre"))
    return genres[:4]


def fetch_fantlab_work_details(work_id: int) -> dict[str, Any]:
    """Загружает детали произведения (аннотацию, жанры, оригинальное название, обложку) с FantLab."""
    if not work_id:
        return {}
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(f"{FANTLAB_WORK_URL}/{work_id}", params={"classificatory": 1})
            if resp.status_code != 200:
                return {}
            w_data = resp.json() or {}
    except Exception:
        return {}

    summary = _strip_html(w_data.get("work_description"))
    genres = _extract_fantlab_genres(w_data)
    raw_orig = (w_data.get("work_name_orig") or "").strip()
    work_name = (w_data.get("work_name") or "").strip()
    if raw_orig.lower() in {"", "novel", "book", "story", "роман", "повесть", "рассказ"} or raw_orig == work_name:
        title_orig = None
    else:
        title_orig = raw_orig

    raw_img = w_data.get("image")
    poster_url: str | None = None
    if isinstance(raw_img, str) and raw_img.strip():
        poster_url = raw_img if raw_img.startswith("http") else f"https://fantlab.ru{raw_img}"

    rating_fl: float | None = None
    r_obj = w_data.get("rating")
    raw_r = (r_obj.get("true_rating") or r_obj.get("rating")) if isinstance(r_obj, dict) else w_data.get("val_midmark")
    try:
        if raw_r and float(raw_r) > 0:
            rating_fl = round(float(raw_r), 2)
    except (TypeError, ValueError):
        rating_fl = None

    return {
        "fantlab_id": int(work_id),
        "rating_fantlab": rating_fl,
        "url_fantlab": f"https://fantlab.ru/work{work_id}",
        "summary": summary,
        "genres": genres,
        "title_orig": title_orig,
        "poster_url": poster_url,
    }


def fetch_fantlab_info(title_ru: str | None, creator: str | None = None) -> dict[str, Any]:
    """Находит книгу на FantLab и возвращает {'rating_fantlab', 'url_fantlab', 'summary', 'genres'}."""
    if not title_ru:
        return {}
    queries = [f"{creator} {title_ru}".strip()] if creator else []
    queries.append(title_ru)

    for q in queries:
        for variant in _query_variants(q):
            try:
                with httpx.Client(timeout=_HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
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

                    details = fetch_fantlab_work_details(int(work_id)) if work_id else {}
                    genres = list(details.get("genres") or [])
                    if not genres and top.get("name_show_im"):
                        genres.append(str(top["name_show_im"]).strip().lower())
                    return {
                        "fantlab_id": int(work_id) if work_id else None,
                        "rating_fantlab": details.get("rating_fantlab") or rating_fl,
                        "url_fantlab": details.get("url_fantlab") or url_fl,
                        "summary": details.get("summary"),
                        "genres": genres,
                        "title_orig": details.get("title_orig"),
                        "poster_url": details.get("poster_url"),
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
        with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
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
