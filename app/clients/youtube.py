from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.utils.urls import extract_youtube_video_id, normalize_url

YOUTUBE_API_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_OEMBED_URL = "https://www.youtube.com/oembed"
USER_AGENT = "PersonalSecondBrainBot/0.4 (https://github.com/personal-db; local)"


class YouTubeClient:
    """Клиент официального YouTube Data API v3 + официальный YouTube oEmbed (работает без ключа)."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (api_key if api_key is not None else settings.youtube_api_key).strip()

    def fetch_video_info(self, url: str) -> dict[str, Any]:
        canonical = normalize_url(url)
        video_id = extract_youtube_video_id(canonical)
        poster_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else None

        # 1. Если задан официальный ключ YouTube Data API v3
        if self.api_key and video_id:
            try:
                with httpx.Client(timeout=12.0, headers={"User-Agent": USER_AGENT}) as client:
                    resp = client.get(
                        YOUTUBE_API_VIDEOS_URL,
                        params={"part": "snippet,contentDetails", "id": video_id, "key": self.api_key},
                    )
                    if resp.status_code == 200:
                        items = resp.json().get("items") or []
                        if items:
                            snippet = items[0].get("snippet") or {}
                            published = snippet.get("publishedAt") or ""
                            year = int(published[:4]) if len(published) >= 4 and published[:4].isdigit() else None
                            tags = [t.strip().lower() for t in (snippet.get("tags") or [])[:8] if t.strip()]
                            return {
                                "canonical_url": canonical,
                                "video_id": video_id,
                                "title": snippet.get("title") or canonical,
                                "creator": snippet.get("channelTitle"),
                                "description": (snippet.get("description") or "").strip() or None,
                                "release_year": year,
                                "poster_url": poster_url,
                                "tags": tags,
                            }
            except Exception:
                pass

        # 2. Официальный YouTube oEmbed (работает всегда и без API-ключа)
        try:
            with httpx.Client(timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
                resp = client.get(YOUTUBE_OEMBED_URL, params={"url": canonical, "format": "json"})
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "canonical_url": canonical,
                        "video_id": video_id,
                        "title": data.get("title") or canonical,
                        "creator": data.get("author_name"),
                        "description": None,
                        "release_year": None,
                        "poster_url": data.get("thumbnail_url") or poster_url,
                        "tags": [],
                    }
        except Exception:
            pass

        return {
            "canonical_url": canonical,
            "video_id": video_id,
            "title": canonical,
            "creator": None,
            "description": None,
            "release_year": None,
            "poster_url": poster_url,
            "tags": [],
        }
