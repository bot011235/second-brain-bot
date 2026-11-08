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

    def _call_json(
        self,
        system_prompt: str,
        user_prompt: str,
        accept: Any = None,
    ) -> dict[str, Any] | None:
        """Вызывает модели по цепочке; если задан accept(parsed) -> bool, неподходящий ответ переходит к следующей модели."""
        if not self.is_configured:
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        models_to_try = [self.model, self.fallback_model, "qwen/qwen3.8-27b"]
        first_parsed: dict[str, Any] | None = None
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
                        if accept is None or accept(parsed):
                            return parsed
                        first_parsed = first_parsed or parsed
            except Exception:
                continue
        return first_parsed

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

        kind_ru = "фильмов, сериалов и аниме" if media_kind == "movie" else "книг"
        sys_prompt = (
            f"Ты разбираешь пост из соцсети и определяешь, о каких {kind_ru} он. "
            "Пост может быть рекомендацией, подборкой, новостью, трейлером, анонсом или обзором — "
            "во всех этих случаях извлеки произведение(я), КОТОРОМУ ПОСВЯЩЁН пост. "
            "ПРАВИЛА: "
            "1) Произведения, упомянутые лишь для сравнения или как студия/прошлые работы "
            "(«кто любит Dark — рекомендую Час дьявола», «студия, снявшая Ковбой Бибоп») — НЕ извлекай. "
            "Если это подборка из нескольких рекомендаций — извлеки все. "
            "2) Название часто указано в «Комментариях автора поста» (например «Сериал «Три-Пайнс», 2022») — "
            "это самый надёжный источник, используй название и год оттуда. "
            "3) Если название не написано, но по сюжету/персонажам/автору книг ты УВЕРЕННО узнаёшь произведение "
            "(например, инспектор Арман Гамаш в канадской деревне → сериал «Три сосны» / «Three Pines», 2022), — "
            "верни его. Если не уверен — не выдумывай. "
            "4) Названия на украинском или других языках переведи в официальное русское или оригинальное "
            "английское название («Час Диявола» → «The Devil's Hour»), чтобы оно нашлось в TMDB/книжных базах. "
            "Верни СТРОГО JSON-объект вида: "
            '{"items": [{"title": "название на русском или английском", "year": 2022}]}. '
            "Поле year — целое число или null. Если произведений нет — {\"items\": []}."
        )

        def _has_items(p: dict[str, Any]) -> bool:
            return isinstance(p.get("items"), list) and len(p["items"]) > 0

        parsed = self._call_json(sys_prompt, text, accept=_has_items)
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
