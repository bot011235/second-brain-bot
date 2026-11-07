from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import settings

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_JSON_BLOCK_RE = re.compile(r"\{.*\}", flags=re.DOTALL)


def _extract_json_dict(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    m = _JSON_BLOCK_RE.search(text)
    if m:
        try:
            parsed = json.loads(m.group(0))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return None


class GroqLLMClient:
    """Клиент Groq API (OpenAI-совместимый JSON mode) с поддержкой fallback-моделей."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (api_key if api_key is not None else settings.groq_api_key).strip()
        self.model = settings.groq_model
        self.fallback_model = settings.groq_fallback_model

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _call_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        if not self.is_configured:
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        models_to_try = [self.model, self.fallback_model, "qwen/qwen3.8-27b"]
        for model in dict.fromkeys(m for m in models_to_try if m):
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt[:6000]},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            }
            try:
                with httpx.Client(timeout=20.0, headers=headers) as client:
                    resp = client.post(GROQ_CHAT_URL, json=payload)
                    if resp.status_code != 200:
                        # Повтор без response_format, если модель не поддерживает строгий json_object
                        payload.pop("response_format", None)
                        resp = client.post(GROQ_CHAT_URL, json=payload)
                        if resp.status_code != 200:
                            continue
                    content = resp.json()["choices"][0]["message"]["content"]
                    parsed = _extract_json_dict(content)
                    if parsed:
                        return parsed
            except Exception:
                continue
        return None

    def summarize_and_tag(
        self,
        *,
        title: str | None,
        text: str | None,
        existing_tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Возвращает {'title_ru': str, 'summary': str, 'tags': list[str]} на русском языке."""
        fallback_title = (title or text or "Заметка").splitlines()[0][:120]
        fallback_summary = (text or "").strip()[:450] or None
        if not self.is_configured or not (title or text):
            return {"title_ru": fallback_title, "summary": fallback_summary, "tags": []}

        existing_str = ", ".join((existing_tags or [])[:40])
        sys_prompt = (
            "Ты помощник для личной базы знаний («Второй мозг»). "
            "Отвечай СТРОГО валидным JSON-объектом вида: "
            '{"title_ru": "короткий понятный заголовок на русском", '
            '"summary": "выжимка сути в 2-3 предложениях на русском", '
            '"tags": ["тег1", "тег2", "тег3"]}. '
            "Теги — в нижнем регистре, 1-2 слова на русском. По возможности переиспользуй существующие теги: "
            f"[{existing_str}]."
        )
        user_prompt = f"Заголовок: {title or ''}\n\nТекст:\n{text or ''}"
        parsed = self._call_json(sys_prompt, user_prompt)
        if not parsed:
            return {"title_ru": fallback_title, "summary": fallback_summary, "tags": []}

        raw_tags = parsed.get("tags")
        tags = [str(t).strip().lower() for t in raw_tags[:5] if str(t).strip()] if isinstance(raw_tags, list) else []
        return {
            "title_ru": str(parsed.get("title_ru") or fallback_title).strip()[:150],
            "summary": str(parsed.get("summary") or fallback_summary or "").strip() or None,
            "tags": tags,
        }

    def extract_media_list(self, text: str, media_kind: str = "movie") -> list[dict[str, Any]]:
        """Извлекает список фильмов или книг из текста поста/видео-подборки."""
        if not self.is_configured or not text.strip():
            return []

        kind_ru = "фильмов и сериалов" if media_kind == "movie" else "книг"
        sys_prompt = (
            f"Извлеки из текста список упомянутых/рекомендуемых {kind_ru}. "
            "Верни СТРОГО JSON-объект вида: "
            '{"items": [{"title": "название", "year": 2022}]}. '
            "Поле year — целое число или null."
        )
        parsed = self._call_json(sys_prompt, text)
        if not parsed or not isinstance(parsed.get("items"), list):
            return []

        out: list[dict[str, Any]] = []
        for item in parsed["items"][:10]:
            if isinstance(item, dict) and item.get("title"):
                yr = item.get("year")
                out.append(
                    {
                        "title": str(item["title"]).strip(),
                        "year": int(yr) if isinstance(yr, int) or (isinstance(yr, str) and yr.isdigit()) else None,
                    }
                )
        return out
