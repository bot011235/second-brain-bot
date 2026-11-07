from __future__ import annotations

import json
from typing import Any


def build_disambiguation_keyboard(item_id: int, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Кнопки выбора из 2–3 кандидатов + 'Ничего не подходит'."""
    num_emojis = ["1️⃣", "2️⃣", "3️⃣"]
    rows: list[list[dict[str, str]]] = []
    for idx, c in enumerate(candidates[:3]):
        emoji = num_emojis[idx]
        title = (c.get("title_ru") or c.get("title_orig") or "Вариант")[:24]
        year = f" ({c['release_year']})" if c.get("release_year") else ""
        c_cat = c.get("category")
        if c_cat == "book":
            extra = (c.get("creator") or "Книга")[:18]
        else:
            extra = "Сериал" if c_cat == "series" else "Фильм"
        rows.append(
            [
                {
                    "text": f"{emoji} {title}{year} · {extra}",
                    "callback_data": f"pick:{item_id}:{idx}",
                }
            ]
        )
    rows.append(
        [
            {"text": "❌ Ничего не подходит", "callback_data": f"pick:{item_id}:none"},
            {"text": "🗑 Удалить", "callback_data": f"del:{item_id}"},
        ]
    )
    return {"inline_keyboard": rows}


def build_item_keyboard(item: dict[str, Any]) -> dict[str, Any]:
    """Строит inline_keyboard для карточки в Telegram (callback_data <= 64 байт)."""
    item_id = item["id"]
    if item.get("processing_status") == "needs_choice":
        raw_meta = item.get("meta")
        if raw_meta:
            try:
                parsed = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
                candidates = list(parsed.get("candidates") or [])
                if candidates:
                    return build_disambiguation_keyboard(item_id, candidates)
            except Exception:
                pass

    current_status = item.get("status", "inbox")

    # Все ссылки на КП / IMDb / RT / FantLab / Goodreads теперь встроены прямо в цифры рейтингов в тексте карточки!
    # В кнопках оставляем только ссылку на исходный пост/видео (если элемент сохранён по ссылке) и кнопки статусов.
    url_row: list[dict[str, str]] = []
    sources = item.get("sources") or []
    for idx, src in enumerate(sources[:2], start=1):
        if src.get("source_url"):
            label = "🔗 Источник" if len(sources) == 1 else f"🔗 Источник {idx}"
            url_row.append({"text": label, "url": str(src["source_url"])})

    status_buttons = [
        ("📌 В планы", "planned"),
        ("▶️ В процессе", "in_progress"),
        ("✅ Готово", "done"),
    ]
    status_row: list[dict[str, str]] = []
    for text, code in status_buttons:
        prefix = "• " if current_status == code else ""
        status_row.append({"text": f"{prefix}{text}", "callback_data": f"st:{item_id}:{code}"})

    action_row = [
        {"text": "🚫 Брошено", "callback_data": f"st:{item_id}:dropped"},
        {"text": "🗑 Удалить", "callback_data": f"del:{item_id}"},
    ]

    keyboard: list[list[dict[str, str]]] = []
    if url_row:
        keyboard.append(url_row)
    keyboard.append(status_row)
    keyboard.append(action_row)
    return {"inline_keyboard": keyboard}
