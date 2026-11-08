from __future__ import annotations

import html
import json
from typing import Any
from urllib.parse import quote_plus

CATEGORY_META: dict[str, tuple[str, str]] = {
    "movie": ("🎬", "Фильм"),
    "series": ("📺", "Сериал"),
    "book": ("📚", "Книга"),
    "video": ("▶️", "YouTube"),
    "article": ("📰", "Статья"),
    "post": ("💬", "Пост"),
    "idea": ("💡", "Идея"),
}

STATUS_LABELS: dict[str, dict[str, str]] = {
    "default": {
        "inbox": "📥 Входящие",
        "planned": "📌 В планах",
        "in_progress": "▶️ В процессе",
        "done": "✅ Готово",
        "dropped": "🚫 Брошено",
    },
    "movie": {
        "inbox": "📥 Входящие",
        "planned": "📌 Хочу посмотреть",
        "in_progress": "▶️ Смотрю",
        "done": "✅ Просмотрено",
        "dropped": "🚫 Брошено",
    },
    "series": {
        "inbox": "📥 Входящие",
        "planned": "📌 Хочу посмотреть",
        "in_progress": "▶️ Смотрю",
        "done": "✅ Просмотрено",
        "dropped": "🚫 Брошено",
    },
    "book": {
        "inbox": "📥 Входящие",
        "planned": "📌 Хочу прочитать",
        "in_progress": "📖 Читаю",
        "done": "✅ Прочитано",
        "dropped": "🚫 Брошено",
    },
}


def format_status_label(category: str, status: str) -> str:
    table = STATUS_LABELS.get(category, STATUS_LABELS["default"])
    return table.get(status, status)


def render_disambiguation_html(query: str, candidates: list[dict[str, Any]]) -> str:
    """Карточка выбора кандидата, когда по названию найдено несколько вариантов."""
    lines = [
        f"🔎 По запросу «<b>{html.escape(query)}</b>» найдено несколько вариантов.",
        "Выберите нужный кнопкой ниже:\n",
    ]
    num_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    for idx, c in enumerate(candidates[:3]):
        emoji = num_emojis[idx]
        c_cat = c.get("category")
        cat_icon = "📚" if c_cat == "book" else ("📺" if c_cat == "series" else "🎬")
        title_ru = html.escape(c.get("title_ru") or "Без названия")
        title_orig = html.escape(c.get("title_orig") or "")
        year = c.get("release_year")
        line = f"{emoji} {cat_icon} <b>{title_ru}</b>"
        if title_orig and title_orig.lower() != title_ru.lower():
            line += f" / <i>{title_orig}</i>"
        if year:
            line += f" ({year})"
        if c.get("creator"):
            line += f" · 👤 {html.escape(str(c['creator']))}"
        if c.get("summary"):
            short_desc = html.escape(str(c["summary"]))[:120]
            line += f"\n   <i>{short_desc}</i>"
        lines.append(line)
    return "\n".join(lines)


def render_card_html(item: dict[str, Any], max_len: int = 1024) -> str:
    """Формирует HTML-карточку для Telegram."""
    if item.get("processing_status") == "needs_choice":
        raw_meta = item.get("meta")
        candidates: list[dict[str, Any]] = []
        if raw_meta:
            try:
                parsed = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
                candidates = list(parsed.get("candidates") or [])
            except Exception:
                candidates = []
        if candidates:
            return render_disambiguation_html(item.get("raw_input") or item.get("title_ru") or "", candidates)

    cat = item.get("category", "idea")
    emoji, _ = CATEGORY_META.get(cat, ("📌", cat))
    title_ru = html.escape(item.get("title_ru") or "Без названия")
    title_orig = html.escape(item.get("title_orig") or "")
    year = item.get("release_year")

    header = f"{emoji} <b>{title_ru}</b>"
    if poster_url := item.get("poster_url"):
        header = f'<a href="{html.escape(str(poster_url))}">&#8205;</a>' + header
    if title_orig and title_orig.lower() != title_ru.lower():
        header += f" / <i>{title_orig}</i>"
    if year:
        header += f" ({year})"

    lines = [header]

    if item.get("creator"):
        lines.append(f"👤 {html.escape(str(item['creator']))}")

    raw_meta = item.get("meta")
    parsed_meta: dict[str, Any] = {}
    if raw_meta:
        try:
            parsed_meta = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
        except Exception:
            parsed_meta = {}

    ratings: list[str] = []
    if cat == "book":
        r_fl = parsed_meta.get("rating_fantlab") or item.get("rating_kp")
        u_fl = parsed_meta.get("url_fantlab")
        if r_fl is not None and u_fl:
            ratings.append(f'🐉 <a href="{html.escape(str(u_fl))}">FantLab <b>{r_fl}</b></a>')
        elif r_fl is not None:
            ratings.append(f"🐉 FantLab <b>{r_fl}</b>")
        elif u_fl:
            ratings.append(f'🐉 <a href="{html.escape(str(u_fl))}">FantLab</a>')

        r_gr = parsed_meta.get("rating_goodreads") or item.get("rating_imdb")
        u_gr = parsed_meta.get("url_goodreads")
        if r_gr is not None and u_gr:
            ratings.append(f'📖 <a href="{html.escape(str(u_gr))}">Goodreads <b>{r_gr}</b></a>')
        elif r_gr is not None:
            ratings.append(f"📖 Goodreads <b>{r_gr}</b>")
        elif u_gr:
            ratings.append(f'📖 <a href="{html.escape(str(u_gr))}">Goodreads</a>')

        if info_link := parsed_meta.get("info_link"):
            ratings.append(f'🌐 <a href="{html.escape(str(info_link))}">Вики</a>')
    elif cat in ("movie", "series"):
        imdb_url = f"https://www.imdb.com/title/{item['imdb_id']}/" if item.get("imdb_id") else None
        if item.get("rating_imdb") is not None and imdb_url:
            ratings.append(f'⭐ <a href="{html.escape(imdb_url)}">IMDb <b>{item["rating_imdb"]}</b></a>')
        elif item.get("rating_imdb") is not None:
            ratings.append(f"⭐ IMDb <b>{item['rating_imdb']}</b>")
        elif imdb_url:
            ratings.append(f'⭐ <a href="{html.escape(imdb_url)}">IMDb</a>')

        kp_query = (item.get("title_ru") or item.get("title_orig") or "").strip()
        kp_url = (
            f"https://www.kinopoisk.ru/film/{item['kp_id']}/"
            if item.get("kp_id")
            else (f"https://www.kinopoisk.ru/index.php?kp_query={quote_plus(kp_query)}" if kp_query else None)
        )
        if item.get("rating_kp") is not None and kp_url:
            ratings.append(f'🟠 <a href="{html.escape(kp_url)}">КП <b>{item["rating_kp"]}</b></a>')
        elif item.get("rating_kp") is not None:
            ratings.append(f"🟠 КП <b>{item['rating_kp']}</b>")
        elif kp_url:
            ratings.append(f'🟠 <a href="{html.escape(kp_url)}">КП</a>')

        tmdb_id = parsed_meta.get("tmdb_id")
        tmdb_type = "tv" if cat == "series" else "movie"
        tmdb_url = f"https://www.themoviedb.org/{tmdb_type}/{tmdb_id}" if tmdb_id else None
        if parsed_meta.get("rating_tmdb") is not None and tmdb_url:
            ratings.append(f'🎞 <a href="{html.escape(tmdb_url)}">TMDB <b>{parsed_meta["rating_tmdb"]}</b></a>')
        elif parsed_meta.get("rating_tmdb") is not None:
            ratings.append(f"🎞 TMDB <b>{parsed_meta['rating_tmdb']}</b>")

        rt_url = item.get("url_rt")
        if item.get("rating_rt") is not None and rt_url:
            ratings.append(f'🍅 <a href="{html.escape(str(rt_url))}">RT <b>{item["rating_rt"]}%</b></a>')
        elif rt_url:
            ratings.append(f'🍅 <a href="{html.escape(str(rt_url))}">RT</a>')

    if ratings:
        lines.append(" · ".join(ratings))

    genres = item.get("genres") or []
    if genres:
        lines.append("🎭 " + " · ".join(f"<code>{html.escape(g)}</code>" for g in genres))

    summary = (item.get("summary") or "").strip()
    if summary:
        escaped_summary = html.escape(summary)
        if len(escaped_summary) > 450:
            escaped_summary = escaped_summary[:447] + "..."
        lines.append(f"\n{escaped_summary}")

    if item.get("processing_status") == "needs_input":
        lines.append("\n⚠️ <i>Не удалось однозначно определить. Ответьте на карточку названием с годом.</i>")

    tags = item.get("tags") or []
    if tags:
        lines.append("\n" + " ".join(f"#{html.escape(t.replace(' ', '_'))}" for t in tags))

    text = "\n".join(lines)
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text
