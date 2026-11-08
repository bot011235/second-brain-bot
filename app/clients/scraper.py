from __future__ import annotations

import html
import json
import re
from typing import Any

import httpx

from app.utils.urls import normalize_url

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_JSON_SCRIPT_RE = re.compile(r'<script type="application/json"[^>]*>(.*?)</script>', flags=re.DOTALL)

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
_THREADS_BODY_RE = re.compile(
    r'<span[^>]*class=["\'][^"\']*BodyTextContainer[^"\']*["\'][^>]*>(.*?)</span>\s*</span>',
    flags=re.IGNORECASE | re.DOTALL,
)
_THREADS_AUTHOR_RE = re.compile(
    r'<div[^>]*class=["\'][^"\']*AuthorIdentity[^"\']*["\'][^>]*>.*?<span[^>]*>(.*?)</span>',
    flags=re.IGNORECASE | re.DOTALL,
)
_THREADS_MEDIA_IMG_RE = re.compile(
    r'<div[^>]*class=["\'][^"\']*(?:SingleInnerMediaContainer|MediaContainer)[^"\']*["\'][^>]*>.*?<img[^>]+src=["\']([^"\']+)["\']',
    flags=re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", flags=re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    val = html.unescape(_TAG_RE.sub(" ", text))
    val = _WS_RE.sub(" ", val).strip()
    return val or None


def _clean_multiline(text: str | None) -> str | None:
    if not text:
        return None
    with_newlines = _BR_RE.sub("\n", text)
    raw = html.unescape(_TAG_RE.sub("", with_newlines))
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.splitlines()]
    cleaned = "\n".join(ln for ln in lines if ln)
    return cleaned or None


def parse_threads_embed(embed_html: str) -> dict[str, str | None]:
    """Извлекает текст поста, автора и картинку из страницы /embed в Threads."""
    text: str | None = None
    m_body = _THREADS_BODY_RE.search(embed_html)
    if m_body:
        text = _clean_multiline(m_body.group(1))

    author: str | None = None
    m_auth = _THREADS_AUTHOR_RE.search(embed_html)
    if m_auth:
        raw_auth = _clean(m_auth.group(1))
        if raw_auth:
            author = f"@{raw_auth.lstrip('@')}"

    image: str | None = None
    m_img = _THREADS_MEDIA_IMG_RE.search(embed_html)
    if m_img:
        image = html.unescape(m_img.group(1)).strip()

    title: str | None = None
    if text:
        first_line = text.splitlines()[0].strip()
        title = first_line[:120] if first_line else None

    return {
        "title": title,
        "description": text,
        "text": text,
        "author": author,
        "image": image,
    }


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


def _walk_threads_posts(node: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(node, dict):
        cap = node.get("caption")
        user = node.get("user")
        if isinstance(cap, dict) and isinstance(cap.get("text"), str) and isinstance(user, dict):
            out.append(
                {
                    "username": str(user.get("username") or ""),
                    "code": node.get("code"),
                    "taken_at": node.get("taken_at") or 0,
                    "text": cap["text"],
                }
            )
        for v in node.values():
            _walk_threads_posts(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_threads_posts(v, out)


def fetch_threads_author_replies(post_url: str, author: str | None, limit: int = 3) -> list[str]:
    """Возвращает ответы автора под его же постом в Threads (там часто пишут название фильма/сериала)."""
    username = (author or "").lstrip("@").strip().lower()
    if not username:
        m = re.search(r"/@([^/]+)/post/", post_url)
        username = m.group(1).lower() if m else ""
    m_code = re.search(r"/post/([^/?#]+)", post_url)
    post_code = m_code.group(1) if m_code else None
    if not username:
        return []
    try:
        # Публичный SSR-рендер для поисковых роботов содержит JSON поста вместе с ответами
        resp = httpx.get(
            post_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"},
            follow_redirects=True,
            timeout=15.0,
        )
        if resp.status_code != 200:
            return []
        posts: list[dict[str, Any]] = []
        for m in _JSON_SCRIPT_RE.finditer(resp.text):
            body = m.group(1)
            if '"caption"' not in body:
                continue
            try:
                _walk_threads_posts(json.loads(body), posts)
            except Exception:
                continue
    except Exception:
        return []

    seen: set[str] = set()
    replies: list[dict[str, Any]] = []
    for p in posts:
        code = str(p.get("code") or "")
        if not code or code in seen or code == post_code:
            continue
        seen.add(code)
        if p["username"].lower() == username and p["text"].strip():
            replies.append(p)
    replies.sort(key=lambda p: p.get("taken_at") or 0)
    return [p["text"].strip()[:400] for p in replies[:limit]]


def scrape_url(url: str) -> dict[str, Any]:
    """Извлекает OpenGraph-метаданные и основной текст статьи/поста по URL (включая редиректы и /embed для Threads)."""
    canonical = normalize_url(url)
    is_threads_or_ig = any(d in canonical.lower() for d in ("threads.net", "threads.com", "instagram.com"))
    initial_ua = "TelegramBot (like TwitterBot)" if is_threads_or_ig else USER_AGENT
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(canonical, headers={"User-Agent": initial_ua})
            resolved_url = normalize_url(str(resp.url)) or canonical
            canonical = resolved_url

            # Для постов Threads используем /embed с базовым WebKit UA (чтобы получить SSR HTML с текстом поста)
            if ("threads.net" in canonical.lower() or "threads.com" in canonical.lower()) and (
                "/post/" in canonical or "/t/" in canonical
            ):
                base_post_url = canonical.split("?")[0].rstrip("/")
                embed_url = base_post_url + "/embed"
                embed_resp = httpx.get(
                    embed_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    follow_redirects=True,
                    timeout=12.0,
                )
                if embed_resp.status_code == 200:
                    t_parsed = parse_threads_embed(embed_resp.text)
                    if t_parsed.get("text"):
                        post_text = str(t_parsed["text"])
                        # Название часто лежит в первом/закреплённом комментарии автора — дотягиваем его ответы
                        author_replies = fetch_threads_author_replies(base_post_url, t_parsed.get("author"))
                        if author_replies:
                            post_text += "\n\nКомментарии автора поста:\n" + "\n".join(
                                f"— {r}" for r in author_replies
                            )
                        return {
                            "canonical_url": base_post_url,
                            "ok": True,
                            "title": t_parsed.get("title"),
                            "description": t_parsed.get("description"),
                            "text": post_text,
                            "author": t_parsed.get("author"),
                            "poster_url": t_parsed.get("image"),
                        }

            if resp.status_code >= 400:
                return {"canonical_url": canonical, "ok": False, "title": None, "text": None}
            raw_html = resp.text
    except Exception:
        return {"canonical_url": canonical, "ok": False, "title": None, "text": None}

    parsed = parse_html_metadata(raw_html)
    title = parsed.get("title")
    desc = parsed.get("description")
    body = parsed.get("body_text")

    # Проверяем, не закрыта ли страница логин-стеной Instagram или пустой заглушкой Threads
    is_login_wall = bool(
        title and title.lower().strip() in ("instagram", "login • instagram", "threads")
    )
    if is_login_wall and not desc and not body:
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
