from __future__ import annotations

from typing import Any

import httpx

from app.config import settings

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


def _parse_year(date_str: str | None) -> int | None:
    if not date_str or len(date_str) < 4:
        return None
    try:
        return int(date_str[:4])
    except ValueError:
        return None


class TMDBClient:
    """Клиент официального TMDB API (themoviedb.org)."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (api_key if api_key is not None else settings.tmdb_api_key).strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = dict(params or {})
        headers = {"Accept": "application/json"}
        # Поддержка и короткого API Key (v3), и длинного Read Access Token (v4 JWT)
        if len(self.api_key) > 60:
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            params["api_key"] = self.api_key

        with httpx.Client(timeout=15.0, headers=headers) as client:
            resp = client.get(f"{TMDB_BASE_URL}{path}", params=params)
            resp.raise_for_status()
            return resp.json()

    def search_candidates(self, query: str, year: int | None = None, limit: int = 5) -> list[dict[str, Any]]:
        """Ищет фильмы и сериалы (и по русскому, и по английскому названию) и возвращает карточку на русском языке."""
        if not self.is_configured:
            return []

        data = self._request(
            "/search/multi",
            {"query": query, "language": "ru-RU", "include_adult": "false", "page": 1},
        )
        raw_list = data.get("results", [])
        # Если по запросу с language=ru-RU ничего не нашлось, пробуем en-US и дотягиваем русские названия
        if not raw_list:
            data = self._request(
                "/search/multi",
                {"query": query, "language": "en-US", "include_adult": "false", "page": 1},
            )
            raw_list = data.get("results", [])

        results: list[dict[str, Any]] = []
        for raw in raw_list:
            media_type = raw.get("media_type")
            if media_type not in ("movie", "tv"):
                continue

            is_tv = media_type == "tv"
            title_ru = raw.get("name") if is_tv else raw.get("title")
            title_orig = raw.get("original_name") if is_tv else raw.get("original_title")
            release_year = _parse_year(raw.get("first_air_date") if is_tv else raw.get("release_date"))

            if year and release_year and abs(release_year - year) > 1:
                continue

            poster_path = raw.get("poster_path")
            results.append(
                {
                    "source": "tmdb",
                    "tmdb_id": raw.get("id"),
                    "media_type": media_type,
                    "category": "series" if is_tv else "movie",
                    "title_ru": title_ru or title_orig or query,
                    "title_orig": title_orig,
                    "release_year": release_year,
                    "summary": (raw.get("overview") or "").strip() or None,
                    "poster_url": f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None,
                    "rating_tmdb": round(float(raw["vote_average"]), 1) if raw.get("vote_average") else None,
                }
            )
            if len(results) >= limit:
                break
        return results

    def find_by_imdb_id(self, imdb_id: str) -> dict[str, Any] | None:
        """Находит точный фильм или сериал в TMDB по imdb_id (например, tt0859163) и возвращает полные детали."""
        if not self.is_configured or not imdb_id:
            return None
        try:
            data = self._request(
                f"/find/{imdb_id}",
                {"external_source": "imdb_id", "language": "ru-RU"},
            )
            movie_res = data.get("movie_results") or []
            if movie_res:
                return self.get_details("movie", int(movie_res[0]["id"]))
            tv_res = data.get("tv_results") or []
            if tv_res:
                return self.get_details("tv", int(tv_res[0]["id"]))
        except Exception:
            return None
        return None

    def get_details(self, media_type: str, tmdb_id: int) -> dict[str, Any]:
        """Загружает полную карточку фильма/сериала из TMDB вместе с external_ids и режиссёром/создателем."""
        data = self._request(
            f"/{media_type}/{tmdb_id}",
            {"language": "ru-RU", "append_to_response": "external_ids,credits"},
        )
        is_tv = media_type == "tv"
        ext = data.get("external_ids") or {}
        imdb_id = ext.get("imdb_id") or data.get("imdb_id")
        wikidata_id = ext.get("wikidata_id")

        genres = [g["name"].strip().lower() for g in data.get("genres", []) if g.get("name")]

        creator: str | None = None
        if is_tv:
            creators = [c.get("name") for c in data.get("created_by", []) if c.get("name")]
            creator = ", ".join(creators[:2]) if creators else None
        else:
            crew = (data.get("credits") or {}).get("crew") or []
            directors = [c.get("name") for c in crew if c.get("job") == "Director" and c.get("name")]
            creator = ", ".join(directors[:2]) if directors else None

        poster_path = data.get("poster_path")
        return {
            "tmdb_id": tmdb_id,
            "media_type": media_type,
            "category": "series" if is_tv else "movie",
            "title_ru": (data.get("name") if is_tv else data.get("title")) or "",
            "title_orig": (data.get("original_name") if is_tv else data.get("original_title")) or None,
            "release_year": _parse_year(data.get("first_air_date") if is_tv else data.get("release_date")),
            "summary": (data.get("overview") or "").strip() or None,
            "poster_url": f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None,
            "genres": genres,
            "creator": creator,
            "imdb_id": imdb_id,
            "wikidata_id": wikidata_id,
            "rating_tmdb": round(float(data["vote_average"]), 1) if data.get("vote_average") else None,
        }
