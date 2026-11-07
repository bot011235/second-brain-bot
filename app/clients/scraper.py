from __future__ import annotations

import html
import re
from typing import Any

import httpx

from app.utils.urls import normalize_url

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_META_PROP_RE = re.compile(
    r'<meta\s+[^>]*?(?:property|name)=["\'](?P<name>og:[a-z_:]+|twitter:[a-z_:]+|description|author)["\'][^>]*?content=["\'](?P<content>[^"\']+)["\']',
    flags=re.IGNORECASE,
)
_META_PROP_REV_RE = re.compile(
    r'<meta\s+[^>]*?content=["\'](?P<content>[^"\']+)["\'][^>]*?(?:property|name)=["\'](?P<name>og:[a-z_:]+|twitter:[a-z_:]+|description|author)["\']',
    flags=re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title[^>]*>(?P<title>.*?)</title>", flags=re.IGNORECASE | re.DOTALL)
_PARAGRAPH_RE = re.compile(r"<p[^>]*>(.*?)</p>", flags=re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    val = html.unescape(_TAG_RE.sub(" ", text))
    val = _WS_RE.sub(" ", val).strip()
    return val or None


def parse_html_metadata(raw_html: str) -> dict[str, str | None]:
    meta: dict[str, str] = {}
    for regex in (_META_PROP_RE, _META_PROP_REV_RE):
        for m in regex.finditer(raw_html):
            k = m.group("name").lower()
            v = html.unescape(m.group("content")).strip()
            if v and k not in meta:
                meta[k] = v

    title = meta.get("og:title") or meta.get("twitter:title")
    if not title:
        t_m = _TITLE_RE.search(raw_html)
        if t_m:
            title = _clean(t_m.group("title"))

    description = meta.get("og:description") or meta.get("twitter:description") or meta.get("description")
    image = meta.get("og:image") or meta.get("twitter:image")
    author = meta.get("author") or meta.get("og:site_name")

    paragraphs: list[str] = []
    for p_m in _PARAGRAPH_RE.finditer(raw_html):
        p_txt = _clean(p_m.group(1))
        if p_txt and len(p_txt) > 40:
            paragraphs.append(p_txt)
        if len(paragraphs) >= 8:
            break
    body_text = "\n".join(paragraphs) if paragraphs else None

    return {
        "title": _clean(title),
        "description": _clean(description),
        "image": image,
        "author": _clean(author),
        "body_text": body_text,
    }


def scrape_url(url: str) -> dict[str, Any]:
    """Извлекает OpenGraph-метаданные и основной текст статьи/поста по URL."""
    canonical = normalize_url(url)
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(canonical)
            if resp.status_code >= 400:
                return {"canonical_url": canonical, "ok": False, "title": None, "text": None}
            raw_html = resp.text
    except Exception:
        return {"canonical_url": canonical, "ok": False, "title": None, "text": None}

    parsed = parse_html_metadata(raw_html)
    title = parsed.get("title")
    desc = parsed.get("description")
    body = parsed.get("body_text")

    # Проверяем, не закрыта ли страница логин-стеной Instagram
    is_login_wall = bool(title and title.lower().strip() in ("instagram", "login • instagram"))
    if is_login_wall and not desc:
        return {"canonical_url": canonical, "ok": False, "title": None, "text": None}

    combined_text = "\n\n".join(part for part in (desc, body) if part)
    return {
        "canonical_url": canonical,
        "ok": bool(title or combined_text),
        "title": title,
        "description": desc,
        "text": combined_text or desc,
        "author": parsed.get("author"),
        "poster_url": parsed.get("image"),
    }
