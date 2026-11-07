from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_STRIP_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "igsh",
    "igshid",
    "si",
    "feature",
    "fbclid",
    "gclid",
    "yclid",
    "mc_cid",
    "mc_eid",
    "_ga",
}

_YT_SHORT_RE = re.compile(r"^/(?:shorts|embed|v)/([A-Za-z0-9_-]{6,15})")


def extract_youtube_video_id(url: str) -> str | None:
    """Извлекает ID видео из любых вариантов ссылок YouTube (watch?v=, youtu.be/, /shorts/)."""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return None

    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]

    if host == "youtu.be":
        vid = parsed.path.lstrip("/").split("/")[0]
        return vid or None

    if host in ("youtube.com", "music.youtube.com"):
        m = _YT_SHORT_RE.match(parsed.path)
        if m:
            return m.group(1)
        qs = dict(parse_qsl(parsed.query))
        if qs.get("v"):
            return qs["v"]
    return None


def normalize_url(raw_url: str) -> str:
    """Канонизирует URL: убирает трекинговые параметры, приводит YouTube и Threads к единому виду."""
    url = raw_url.strip().rstrip(".,;)>]")
    yt_id = extract_youtube_video_id(url)
    if yt_id:
        return f"https://www.youtube.com/watch?v={yt_id}"

    try:
        parsed = urlparse(url)
    except Exception:
        return url

    scheme = (parsed.scheme or "https").lower()
    host = (parsed.netloc or "").lower()
    if host.startswith("m."):
        host = host[2:]
    if host in ("threads.net", "www.threads.net"):
        host = "www.threads.com"
    elif host == "threads.com":
        host = "www.threads.com"

    clean_Pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if k.lower() not in _STRIP_PARAMS and not k.lower().startswith("utm_")
    ]
    clean_query = urlencode(clean_Pairs)
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    return urlunparse((scheme, host, path, "", clean_query, ""))
