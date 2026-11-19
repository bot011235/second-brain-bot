from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from app.utils.normalize import normalize_text

VALID_STATUSES = ("inbox", "planned", "in_progress", "done", "dropped")

ITEM_COLUMNS = (
    "id",
    "category",
    "status",
    "processing_status",
    "processing_error",
    "title_ru",
    "title_orig",
    "normalized_title",
    "release_year",
    "creator",
    "normalized_creator",
    "imdb_id",
    "kp_id",
    "google_books_id",
    "isbn13",
    "canonical_url",
    "rating_imdb",
    "rating_kp",
    "rating_rt",
    "user_rating",
    "summary",
    "poster_url",
    "poster_tg_file_id",
    "url_rt",
    "meta",
    "raw_input",
    "tg_topic_id",
    "tg_message_id",
    "created_at",
    "updated_at",
)


def _row_to_item(row: tuple[Any, ...] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(zip(ITEM_COLUMNS, row))


def _parse_meta_dict(raw_meta: Any) -> dict[str, Any]:
    if isinstance(raw_meta, dict):
        return dict(raw_meta)
    if isinstance(raw_meta, str) and raw_meta.strip():
        try:
            parsed = json.loads(raw_meta)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _sanitize_highlights(raw_highlights: list[Any]) -> list[dict[str, Any]]:
    if not isinstance(raw_highlights, list):
        raise ValueError("Invalid highlights")
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    cleaned: list[dict[str, Any]] = []
    for entry in raw_highlights[:100]:
        if isinstance(entry, str):
            raw_text = entry
            raw_note = ""
            raw_id = ""
            raw_created = ""
        elif isinstance(entry, dict):
            raw_text = str(entry.get("text") or "")
            raw_note = str(entry.get("note") or "")
            raw_id = str(entry.get("id") or "").strip()
            raw_created = str(entry.get("created_at") or "").strip()
        else:
            continue
        text = raw_text.strip()[:4000]
        if not text:
            continue
        note = raw_note.strip()[:1000]
        hl: dict[str, Any] = {
            "id": raw_id or f"hl-{len(cleaned) + 1}",
            "text": text,
            "created_at": raw_created or now_iso,
        }
        if note:
            hl["note"] = note
        cleaned.append(hl)
    return cleaned


def _sanitize_progress(raw_progress: Any) -> dict[str, Any] | None:
    if not isinstance(raw_progress, dict):
        raise ValueError("Invalid progress")
    if not raw_progress or raw_progress.get("clear") is True:
        return None
    kind = str(raw_progress.get("kind") or "").strip().lower()
    if kind not in ("series", "book", "read"):
        raise ValueError("Invalid progress kind")
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        if kind == "series":
            season = max(1, min(999, int(raw_progress.get("season") or 1)))
            episode = max(0, min(9999, int(raw_progress.get("episode") or 0)))
            res: dict[str, Any] = {
                "kind": "series",
                "season": season,
                "episode": episode,
                "updated_at": now_iso,
            }
            total_seasons = raw_progress.get("total_seasons")
            if total_seasons is not None and int(total_seasons) > 0:
                res["total_seasons"] = min(999, int(total_seasons))
            return res
        if kind == "book":
            page = max(0, min(99999, int(raw_progress.get("page") or 0)))
            total_pages = max(0, min(99999, int(raw_progress.get("total_pages") or 0)))
            percent = (
                min(100, round(page * 100 / total_pages))
                if total_pages > 0
                else max(0, min(100, int(raw_progress.get("percent") or 0)))
            )
            return {
                "kind": "book",
                "page": page,
                "total_pages": total_pages,
                "percent": percent,
                "updated_at": now_iso,
            }
        scroll_pct = max(0, min(100, int(raw_progress.get("scroll_pct") or 0)))
        return {
            "kind": "read",
            "scroll_pct": scroll_pct,
            "updated_at": now_iso,
        }
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid progress value") from exc


def mark_update_processed(conn: Any, update_id: int) -> bool:
    """Возвращает True, если update_id ещё не обрабатывался (и помечает его обработанным)."""
    cur = conn.execute("SELECT 1 FROM processed_updates WHERE update_id = ?", (update_id,))
    if cur.fetchone() is not None:
        return False
    conn.execute("INSERT INTO processed_updates (update_id) VALUES (?)", (update_id,))
    conn.commit()
    return True


def sync_item_fts(conn: Any, item_id: int) -> None:
    """Пересобирает строку в items_fts для указанного item_id."""
    conn.execute("DELETE FROM items_fts WHERE rowid = ?", (item_id,))
    cur = conn.execute(
        "SELECT title_ru, title_orig, creator, summary, meta FROM items WHERE id = ?",
        (item_id,),
    )
    row = cur.fetchone()
    if row is None:
        conn.commit()
        return

    title_ru, title_orig, creator, summary, raw_meta = row
    tags_cur = conn.execute("SELECT tag FROM item_tags WHERE item_id = ?", (item_id,))
    tags_str = " ".join(r[0] for r in tags_cur.fetchall() if r[0])

    sources_cur = conn.execute("SELECT raw_text FROM item_sources WHERE item_id = ?", (item_id,))
    sources_parts = [r[0] for r in sources_cur.fetchall() if r[0]]
    meta_obj = _parse_meta_dict(raw_meta)
    if meta_obj.get("user_note"):
        sources_parts.append(str(meta_obj["user_note"]))
    if isinstance(meta_obj.get("highlights"), list):
        for hl in meta_obj["highlights"]:
            if isinstance(hl, dict):
                if hl.get("text"):
                    sources_parts.append(str(hl["text"]))
                if hl.get("note"):
                    sources_parts.append(str(hl["note"]))
            elif isinstance(hl, str) and hl.strip():
                sources_parts.append(hl.strip())
    sources_str = " ".join(sources_parts)

    conn.execute(
        """
        INSERT INTO items_fts (rowid, title_ru, title_orig, creator, summary, tags, sources_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item_id,
            title_ru or "",
            title_orig or "",
            creator or "",
            summary or "",
            tags_str,
            sources_str,
        ),
    )
    conn.commit()


def create_item(
    conn: Any,
    *,
    category: str,
    title_ru: str | None = None,
    title_orig: str | None = None,
    raw_input: str | None = None,
    summary: str | None = None,
    creator: str | None = None,
    release_year: int | None = None,
    status: str = "inbox",
    processing_status: str = "ok",
    tg_topic_id: int | None = None,
    tg_message_id: int | None = None,
    source_url: str | None = None,
    source_type: str = "manual",
    imdb_id: str | None = None,
    kp_id: int | None = None,
    google_books_id: str | None = None,
    isbn13: str | None = None,
    canonical_url: str | None = None,
    rating_imdb: float | None = None,
    rating_kp: float | None = None,
    rating_rt: int | None = None,
    poster_url: str | None = None,
    url_rt: str | None = None,
    genres: list[str] | None = None,
    tags: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    display_title = title_ru or title_orig or (raw_input or "").strip() or "Без названия"
    norm_title = normalize_text(display_title) or "untitled"
    norm_creator = normalize_text(creator) if creator else None
    meta_json = json.dumps(meta, ensure_ascii=False) if meta else None

    cur = conn.execute(
        """
        INSERT INTO items (
            category, status, processing_status,
            title_ru, title_orig, normalized_title,
            release_year, creator, normalized_creator,
            imdb_id, kp_id, google_books_id, isbn13, canonical_url,
            rating_imdb, rating_kp, rating_rt,
            summary, poster_url, url_rt, meta, raw_input,
            tg_topic_id, tg_message_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            category,
            status,
            processing_status,
            title_ru or display_title,
            title_orig,
            norm_title,
            release_year,
            creator,
            norm_creator,
            imdb_id,
            kp_id,
            google_books_id,
            isbn13,
            canonical_url,
            rating_imdb,
            rating_kp,
            rating_rt,
            summary,
            poster_url,
            url_rt,
            meta_json,
            raw_input,
            tg_topic_id,
            tg_message_id,
        ),
    )
    item_id = int(cur.lastrowid)

    conn.execute(
        """
        INSERT INTO item_sources (item_id, source_url, source_type, raw_text)
        VALUES (?, ?, ?, ?)
        """,
        (item_id, source_url, source_type, raw_input),
    )
    set_item_tags(conn, item_id, genres=genres, tags=tags, commit=False)
    conn.commit()
    sync_item_fts(conn, item_id)
    item = get_item(conn, item_id)
    assert item is not None
    return item


def set_item_tags(
    conn: Any,
    item_id: int,
    *,
    genres: list[str] | None = None,
    tags: list[str] | None = None,
    commit: bool = True,
) -> None:
    if genres is not None:
        conn.execute("DELETE FROM item_tags WHERE item_id = ? AND kind = 'genre'", (item_id,))
        for g in genres:
            clean = g.strip().lower()
            if clean:
                conn.execute(
                    "INSERT OR IGNORE INTO item_tags (item_id, kind, tag) VALUES (?, 'genre', ?)",
                    (item_id, clean),
                )
    if tags is not None:
        conn.execute("DELETE FROM item_tags WHERE item_id = ? AND kind = 'tag'", (item_id,))
        for t in tags:
            clean = t.strip().lower()
            if clean:
                conn.execute(
                    "INSERT OR IGNORE INTO item_tags (item_id, kind, tag) VALUES (?, 'tag', ?)",
                    (item_id, clean),
                )
    if commit:
        conn.commit()


def find_existing_movie(
    conn: Any,
    *,
    kp_id: int | None = None,
    imdb_id: str | None = None,
    title_ru: str | None = None,
    release_year: int | None = None,
    exclude_item_id: int | None = None,
) -> dict[str, Any] | None:
    """Ищет существующий фильм/сериал в БД по kp_id, imdb_id или (normalized_title + release_year)."""
    excl_sql = " AND id <> ?" if exclude_item_id is not None else ""
    excl_args: tuple[Any, ...] = (exclude_item_id,) if exclude_item_id is not None else ()

    if kp_id:
        cur = conn.execute(f"SELECT id FROM items WHERE kp_id = ?{excl_sql}", (kp_id, *excl_args))
        row = cur.fetchone()
        if row:
            return get_item(conn, int(row[0]))

    if imdb_id:
        cur = conn.execute(f"SELECT id FROM items WHERE imdb_id = ?{excl_sql}", (imdb_id, *excl_args))
        row = cur.fetchone()
        if row:
            return get_item(conn, int(row[0]))

    if title_ru and release_year:
        norm = normalize_text(title_ru)
        if norm:
            cur = conn.execute(
                f"""
                SELECT id FROM items
                WHERE category IN ('movie', 'series')
                  AND processing_status = 'ok'
                  AND normalized_title = ?
                  AND release_year = ?{excl_sql}
                """,
                (norm, release_year, *excl_args),
            )
            row = cur.fetchone()
            if row:
                return get_item(conn, int(row[0]))

    return None


def find_existing_book(
    conn: Any,
    *,
    google_books_id: str | None = None,
    title_ru: str | None = None,
    creator: str | None = None,
    exclude_item_id: int | None = None,
) -> dict[str, Any] | None:
    """Ищет существующую книгу в БД по google_books_id или (normalized_title + normalized_creator)."""
    excl_sql = " AND id <> ?" if exclude_item_id is not None else ""
    excl_args: tuple[Any, ...] = (exclude_item_id,) if exclude_item_id is not None else ()

    if google_books_id:
        cur = conn.execute(f"SELECT id FROM items WHERE google_books_id = ?{excl_sql}", (google_books_id, *excl_args))
        row = cur.fetchone()
        if row:
            return get_item(conn, int(row[0]))

    if title_ru:
        norm_t = normalize_text(title_ru)
        norm_c = normalize_text(creator) if creator else None
        if norm_t and norm_c:
            cur = conn.execute(
                f"""
                SELECT id FROM items
                WHERE category = 'book'
                  AND processing_status = 'ok'
                  AND normalized_title = ?
                  AND normalized_creator = ?{excl_sql}
                """,
                (norm_t, norm_c, *excl_args),
            )
            row = cur.fetchone()
            if row:
                return get_item(conn, int(row[0]))

    return None


def add_source_to_item(
    conn: Any,
    item_id: int,
    *,
    source_url: str | None,
    source_type: str,
    raw_text: str | None,
) -> None:
    if source_url:
        conn.execute(
            """
            INSERT OR IGNORE INTO item_sources (item_id, source_url, source_type, raw_text)
            VALUES (?, ?, ?, ?)
            """,
            (item_id, source_url, source_type, raw_text),
        )
    else:
        conn.execute(
            """
            INSERT INTO item_sources (item_id, source_url, source_type, raw_text)
            VALUES (?, NULL, ?, ?)
            """,
            (item_id, source_type, raw_text),
        )
    conn.commit()
    sync_item_fts(conn, item_id)


def update_item_enriched(
    conn: Any,
    item_id: int,
    *,
    category: str,
    title_ru: str,
    title_orig: str | None = None,
    release_year: int | None = None,
    creator: str | None = None,
    summary: str | None = None,
    poster_url: str | None = None,
    imdb_id: str | None = None,
    kp_id: int | None = None,
    google_books_id: str | None = None,
    isbn13: str | None = None,
    canonical_url: str | None = None,
    rating_imdb: float | None = None,
    rating_kp: float | None = None,
    rating_rt: int | None = None,
    url_rt: str | None = None,
    genres: list[str] | None = None,
    tags: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    processing_status: str = "ok",
    preserve_user_meta: bool = True,
) -> dict[str, Any] | None:
    cur_row = conn.execute(
        "SELECT imdb_id, kp_id, google_books_id, canonical_url, meta FROM items WHERE id = ?",
        (item_id,),
    ).fetchone()
    if cur_row is None:
        return None
    prev_imdb, prev_kp, prev_gb, prev_canonical, prev_raw_meta = cur_row

    def _safe_unique(col: str, candidate_val: Any, fallback_val: Any) -> Any:
        if candidate_val is None or candidate_val == "":
            return fallback_val
        clash = conn.execute(
            f"SELECT id FROM items WHERE {col} = ? AND id <> ? LIMIT 1",
            (candidate_val, item_id),
        ).fetchone()
        return fallback_val if clash else candidate_val

    safe_imdb = _safe_unique("imdb_id", imdb_id, prev_imdb) if imdb_id is not None else imdb_id
    safe_kp = _safe_unique("kp_id", kp_id, prev_kp) if kp_id is not None else kp_id
    safe_gb = _safe_unique("google_books_id", google_books_id, prev_gb) if google_books_id is not None else google_books_id
    safe_canonical = _safe_unique("canonical_url", canonical_url, prev_canonical) if canonical_url is not None else prev_canonical

    merged_meta = dict(meta) if isinstance(meta, dict) else {}
    if preserve_user_meta:
        prev_meta = _parse_meta_dict(prev_raw_meta)
        for key in ("user_note", "highlights", "progress"):
            if key in prev_meta and key not in merged_meta:
                merged_meta[key] = prev_meta[key]

    norm_title = normalize_text(title_ru or title_orig or "") or "untitled"
    norm_creator = normalize_text(creator) if creator else None
    meta_json = json.dumps(merged_meta, ensure_ascii=False) if merged_meta else None

    conn.execute(
        """
        UPDATE items SET
            category = ?,
            processing_status = ?,
            processing_error = NULL,
            title_ru = ?,
            title_orig = ?,
            normalized_title = ?,
            release_year = ?,
            creator = ?,
            normalized_creator = ?,
            imdb_id = ?,
            kp_id = ?,
            google_books_id = ?,
            isbn13 = ?,
            canonical_url = ?,
            rating_imdb = ?,
            rating_kp = ?,
            rating_rt = ?,
            summary = ?,
            poster_url = ?,
            url_rt = ?,
            meta = ?
        WHERE id = ?
        """,
        (
            category,
            processing_status,
            title_ru,
            title_orig,
            norm_title,
            release_year,
            creator,
            norm_creator,
            safe_imdb,
            safe_kp,
            safe_gb,
            isbn13,
            safe_canonical,
            rating_imdb,
            rating_kp,
            rating_rt,
            summary,
            poster_url,
            url_rt,
            meta_json,
            item_id,
        ),
    )
    set_item_tags(conn, item_id, genres=genres, tags=tags, commit=False)
    conn.commit()
    sync_item_fts(conn, item_id)
    return get_item(conn, item_id)


def upsert_extracted_text_for_item(
    conn: Any,
    item: dict[str, Any],
    *,
    extracted_text: str,
    source_url: str | None = None,
    author: str | None = None,
) -> None:
    """Обновляет или добавляет извлечённый текст источника в original_messages для карточки."""
    clean_text = (extracted_text or "").strip()
    if not clean_text:
        return
    clauses: list[str] = []
    params: list[Any] = []
    eff_url = source_url or item.get("canonical_url")
    if eff_url:
        clauses.append("source_url = ?")
        params.append(eff_url)
    if item.get("tg_message_id") is not None:
        clauses.append("tg_message_id = ?")
        params.append(int(item["tg_message_id"]))
    if clauses:
        row = conn.execute(
            f"SELECT id FROM original_messages WHERE {' OR '.join(clauses)} ORDER BY id DESC LIMIT 1",
            params,
        ).fetchone()
        if row:
            if author:
                conn.execute(
                    "UPDATE original_messages SET extracted_text = ?, author = COALESCE(NULLIF(author, ''), ?) WHERE id = ?",
                    (clean_text, author, int(row[0])),
                )
            else:
                conn.execute(
                    "UPDATE original_messages SET extracted_text = ? WHERE id = ?",
                    (clean_text, int(row[0])),
                )
            conn.commit()
            return
    cat = (item.get("category") or "").lower()
    slug = (
        "movies"
        if cat in ("movie", "series")
        else "books"
        if cat == "book"
        else "video"
        if cat == "video"
        else "article"
        if cat == "article"
        else "ideas"
    )
    create_original_message(
        conn,
        topic_slug=slug,
        raw_text=item.get("raw_input") or item.get("canonical_url") or item.get("title_ru") or "",
        tg_topic_id=item.get("tg_topic_id"),
        tg_message_id=item.get("tg_message_id"),
        source_url=eff_url,
        source_type="web",
        author=author or item.get("creator"),
        extracted_text=clean_text,
    )


def get_item(conn: Any, item_id: int) -> dict[str, Any] | None:
    cols = ", ".join(ITEM_COLUMNS)
    cur = conn.execute(f"SELECT {cols} FROM items WHERE id = ?", (item_id,))
    item = _row_to_item(cur.fetchone())
    if item is None:
        return None

    tags_cur = conn.execute("SELECT kind, tag FROM item_tags WHERE item_id = ? ORDER BY tag", (item_id,))
    tag_rows = tags_cur.fetchall()
    item["genres"] = [r[1] for r in tag_rows if r[0] == "genre"]
    item["tags"] = [r[1] for r in tag_rows if r[0] == "tag"]

    src_cur = conn.execute(
        "SELECT id, source_url, source_type, raw_text, added_at FROM item_sources WHERE item_id = ? ORDER BY id",
        (item_id,),
    )
    item["sources"] = [
        {"id": r[0], "source_url": r[1], "source_type": r[2], "raw_text": r[3], "added_at": r[4]}
        for r in src_cur.fetchall()
    ]

    extracted_text: str | None = None
    orig_clauses: list[str] = []
    orig_params: list[Any] = []
    if item.get("canonical_url"):
        orig_clauses.append("source_url = ?")
        orig_params.append(item["canonical_url"])
    if item.get("tg_message_id") is not None:
        orig_clauses.append("tg_message_id = ?")
        orig_params.append(int(item["tg_message_id"]))
    if orig_clauses:
        ext_row = conn.execute(
            f"""
            SELECT extracted_text FROM original_messages
            WHERE ({' OR '.join(orig_clauses)})
              AND extracted_text IS NOT NULL
              AND TRIM(extracted_text) <> ''
            ORDER BY id DESC
            LIMIT 1
            """,
            orig_params,
        ).fetchone()
        if ext_row:
            extracted_text = ext_row[0]
    item["extracted_text"] = extracted_text
    return item


def update_item_status(conn: Any, item_id: int, status: str) -> dict[str, Any] | None:
    conn.execute("UPDATE items SET status = ? WHERE id = ?", (status, item_id))
    conn.commit()
    return get_item(conn, item_id)


def set_item_tg_message_id(conn: Any, item_id: int, tg_message_id: int) -> None:
    conn.execute("UPDATE items SET tg_message_id = ? WHERE id = ?", (tg_message_id, item_id))
    conn.commit()


def delete_item(conn: Any, item_id: int) -> bool:
    """Удаляет карточку только из каталога (items и items_fts), не затрагивая архив оригиналов."""
    conn.execute("DELETE FROM items_fts WHERE rowid = ?", (item_id,))
    cur = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    return cur.rowcount > 0


def find_existing_by_url(conn: Any, canonical_url: str) -> dict[str, Any] | None:
    """Ищет запись по canonical_url в items или source_url в item_sources."""
    cur = conn.execute("SELECT id FROM items WHERE canonical_url = ?", (canonical_url,))
    row = cur.fetchone()
    if row:
        return get_item(conn, int(row[0]))

    cur = conn.execute("SELECT item_id FROM item_sources WHERE source_url = ? LIMIT 1", (canonical_url,))
    row = cur.fetchone()
    if row:
        return get_item(conn, int(row[0]))
    return None


def list_existing_tags(conn: Any, limit: int = 40) -> list[str]:
    cur = conn.execute(
        "SELECT tag, COUNT(*) AS cnt FROM item_tags WHERE kind = 'tag' GROUP BY tag ORDER BY cnt DESC LIMIT ?",
        (limit,),
    )
    return [r[0] for r in cur.fetchall()]


def update_item_fields(
    conn: Any,
    item_id: int,
    *,
    status: str | None = None,
    user_rating: int | None = None,
    title_ru: str | None = None,
    summary: str | None = None,
    user_note: str | None = None,
    tags: list[str] | None = None,
    highlights: list[dict[str, Any]] | None = None,
    progress: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    cur_item = get_item(conn, item_id)
    if not cur_item:
        return None

    fts_dirty = False
    meta_dict = _parse_meta_dict(cur_item.get("meta"))
    meta_dirty = False

    if user_note is not None:
        clean_note = user_note.strip()
        if clean_note:
            meta_dict["user_note"] = clean_note
        else:
            meta_dict.pop("user_note", None)
        meta_dirty = True
        fts_dirty = True

    if highlights is not None:
        cleaned_hl = _sanitize_highlights(highlights)
        if cleaned_hl:
            meta_dict["highlights"] = cleaned_hl
        else:
            meta_dict.pop("highlights", None)
        meta_dirty = True
        fts_dirty = True

    if progress is not None:
        cleaned_prog = _sanitize_progress(progress)
        if cleaned_prog is not None:
            meta_dict["progress"] = cleaned_prog
        else:
            meta_dict.pop("progress", None)
        meta_dirty = True

    if status is not None:
        conn.execute("UPDATE items SET status = ? WHERE id = ?", (status, item_id))
    if user_rating is not None:
        val = None if user_rating == 0 else int(user_rating)
        conn.execute("UPDATE items SET user_rating = ? WHERE id = ?", (val, item_id))
    if title_ru is not None:
        clean_title = title_ru.strip() or cur_item["title_ru"]
        norm_title = normalize_text(clean_title) or "untitled"
        conn.execute(
            "UPDATE items SET title_ru = ?, normalized_title = ? WHERE id = ?",
            (clean_title, norm_title, item_id),
        )
        fts_dirty = True
    if summary is not None:
        clean_summary = summary.strip() or None
        conn.execute("UPDATE items SET summary = ? WHERE id = ?", (clean_summary, item_id))
        fts_dirty = True
    if meta_dirty:
        meta_json = json.dumps(meta_dict, ensure_ascii=False) if meta_dict else None
        conn.execute("UPDATE items SET meta = ? WHERE id = ?", (meta_json, item_id))
    if tags is not None:
        set_item_tags(conn, item_id, tags=tags, commit=False)
        fts_dirty = True

    conn.commit()
    if fts_dirty:
        sync_item_fts(conn, item_id)
    return get_item(conn, item_id)


def _build_fts_prefix_query(raw_q: str) -> str:
    """Формирует безопасный FTS5 префиксный запрос без спецсимволов."""
    cleaned = str(raw_q or "").replace("#", " ")
    raw_tokens = re.findall(r"[\w]+", cleaned, flags=re.UNICODE)
    if not raw_tokens:
        return ""
    tokens = [t for t in raw_tokens if len(t) >= 2]
    if not tokens:
        tokens = raw_tokens[:1]
    return " AND ".join(f'"{t}"*' for t in tokens[:6])


def _build_catalog_where(
    *,
    tab: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    smart: str | None = None,
) -> tuple[str, list[Any]]:
    """Строит SQL WHERE и параметры для каталога, подсчёта total и счётчиков статусов."""
    where_clauses: list[str] = []
    params: list[Any] = []

    if tab == "movies":
        where_clauses.append("i.category IN ('movie', 'series')")
    elif tab == "books":
        where_clauses.append("i.category = 'book'")
    elif tab == "video":
        where_clauses.append("i.category = 'video'")
    elif tab == "article":
        where_clauses.append("i.category = 'article'")
    elif tab == "ideas":
        where_clauses.append("i.category IN ('idea', 'post')")
    elif tab == "attention":
        where_clauses.append("i.processing_status <> 'ok'")

    if smart == "top_planned":
        where_clauses.append(
            "i.status IN ('inbox', 'planned') AND ("
            "COALESCE(i.rating_imdb, 0) >= 7.5 OR "
            "COALESCE(i.rating_kp, 0) >= 7.5 OR "
            "(i.category = 'book' AND COALESCE(i.rating_imdb, 0) >= 4.0)"
            ")"
        )
    elif smart == "favorites":
        where_clauses.append("COALESCE(i.user_rating, 0) >= 8")
    elif smart == "noted":
        where_clauses.append('(i.meta LIKE \'%"user_note"%\' OR i.meta LIKE \'%"highlights"%\')')
    elif smart == "unrated_done":
        where_clauses.append("i.status = 'done' AND i.user_rating IS NULL")
    elif smart == "attention":
        where_clauses.append("i.processing_status <> 'ok'")

    if status and status != "all":
        where_clauses.append("i.status = ?")
        params.append(status)

    if tag:
        tag_list = [t.strip().lstrip("#").lower() for t in str(tag).split(",") if t.strip().lstrip("#")]
        for t_val in tag_list:
            where_clauses.append("EXISTS (SELECT 1 FROM item_tags t WHERE t.item_id = i.id AND t.tag = ?)")
            params.append(t_val)

    if q and q.strip():
        norm_q = normalize_text(q)
        like_q = f"%{norm_q or q.strip().lower()}%"
        raw_like = f"%{q.strip()}%"
        clean_tag_q = q.strip().lstrip("#").lower()
        tag_like = f"%{clean_tag_q}%"
        q_clauses = [
            "i.normalized_title LIKE ?",
            "i.normalized_creator LIKE ?",
            "i.title_ru LIKE ?",
            "i.title_orig LIKE ?",
            "i.summary LIKE ?",
            "i.meta LIKE ?",
            "EXISTS (SELECT 1 FROM item_tags t WHERE t.item_id = i.id AND t.tag LIKE ?)",
        ]
        q_params: list[Any] = [like_q, like_q, raw_like, raw_like, raw_like, raw_like, tag_like]
        fts_query = _build_fts_prefix_query(q)
        if fts_query:
            q_clauses.append("i.id IN (SELECT rowid FROM items_fts WHERE items_fts MATCH ?)")
            q_params.append(fts_query)
        where_clauses.append("(" + " OR ".join(q_clauses) + ")")
        params.extend(q_params)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    return where_sql, params


def count_items_catalog(
    conn: Any,
    *,
    tab: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    smart: str | None = None,
) -> int:
    """Возвращает общее количество записей под заданными фильтрами без учёта пагинации."""
    where_sql, params = _build_catalog_where(tab=tab, status=status, tag=tag, q=q, smart=smart)
    row = conn.execute(f"SELECT COUNT(*) FROM items i {where_sql}", params).fetchone()
    return int(row[0] or 0) if row else 0


def get_status_counts_by_tab(conn: Any, *, tab: str | None = None) -> dict[str, int]:
    """Возвращает реальные счётчики статусов по всей категории (независимо от LIMIT/OFFSET)."""
    where_sql, params = _build_catalog_where(tab=tab)
    rows = conn.execute(
        f"SELECT COALESCE(i.status, 'inbox'), COUNT(*) FROM items i {where_sql} GROUP BY COALESCE(i.status, 'inbox')",
        params,
    ).fetchall()
    counts = {"all": 0, "inbox": 0, "planned": 0, "in_progress": 0, "done": 0, "dropped": 0}
    for st_val, cnt in rows:
        cnt_int = int(cnt or 0)
        counts["all"] += cnt_int
        key = str(st_val) if str(st_val) in counts else "inbox"
        counts[key] += cnt_int
    return counts


def list_items_catalog(
    conn: Any,
    *,
    tab: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    sort: str = "created",
    limit: int = 200,
    offset: int = 0,
    smart: str | None = None,
) -> list[dict[str, Any]]:
    """Выборка элементов для витрины Telegram Mini App с фильтрацией, поиском, сортировкой и пагинацией."""
    where_sql, params = _build_catalog_where(tab=tab, status=status, tag=tag, q=q, smart=smart)

    sort_map = {
        "created": "i.created_at DESC, i.id DESC",
        "updated": "COALESCE(i.updated_at, i.created_at) DESC, i.id DESC",
        "imdb": "COALESCE(i.rating_imdb, -1) DESC, i.id DESC",
        "kp": "COALESCE(i.rating_kp, -1) DESC, i.id DESC",
        "rt": "COALESCE(i.rating_rt, -1) DESC, i.id DESC",
        "user": "COALESCE(i.user_rating, -1) DESC, i.id DESC",
        "year": "COALESCE(i.release_year, -1) DESC, i.id DESC",
        "title": "i.normalized_title ASC, i.id DESC",
    }
    order_sql = sort_map.get(sort, sort_map["created"])
    safe_offset = max(0, int(offset))

    cols = ", ".join(f"i.{c}" for c in ITEM_COLUMNS)
    cur = conn.execute(
        f"SELECT {cols} FROM items i {where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?",
        (*params, limit, safe_offset),
    )
    items: list[dict[str, Any]] = []
    by_id: dict[int, dict[str, Any]] = {}
    for row in cur.fetchall():
        item = _row_to_item(row)
        if not item:
            continue
        item["genres"] = []
        item["tags"] = []
        item["sources"] = []
        items.append(item)
        by_id[int(item["id"])] = item

    if not items:
        return items

    all_ids = list(by_id.keys())
    chunk_size = 400
    for start in range(0, len(all_ids), chunk_size):
        chunk = all_ids[start : start + chunk_size]
        placeholders = ", ".join("?" for _ in chunk)

        tags_cur = conn.execute(
            f"SELECT item_id, kind, tag FROM item_tags WHERE item_id IN ({placeholders}) ORDER BY tag",
            chunk,
        )
        for item_id, kind, tag_val in tags_cur.fetchall():
            target = by_id.get(int(item_id))
            if not target:
                continue
            if kind == "genre":
                target["genres"].append(tag_val)
            elif kind == "tag":
                target["tags"].append(tag_val)

        src_cur = conn.execute(
            f"SELECT id, item_id, source_url, source_type, raw_text, added_at "
            f"FROM item_sources WHERE item_id IN ({placeholders}) ORDER BY id",
            chunk,
        )
        for src_id, item_id, source_url, source_type, raw_text, added_at in src_cur.fetchall():
            target = by_id.get(int(item_id))
            if target:
                target["sources"].append(
                    {
                        "id": src_id,
                        "source_url": source_url,
                        "source_type": source_type,
                        "raw_text": raw_text,
                        "added_at": added_at,
                    }
                )

    return items


def list_tags_catalog(conn: Any, tab: str | None = None) -> list[dict[str, Any]]:
    cat_filter = ""
    if tab == "movies":
        cat_filter = "WHERE i.category IN ('movie', 'series')"
    elif tab == "books":
        cat_filter = "WHERE i.category = 'book'"
    elif tab == "video":
        cat_filter = "WHERE i.category = 'video'"
    elif tab == "article":
        cat_filter = "WHERE i.category = 'article'"
    elif tab == "ideas":
        cat_filter = "WHERE i.category IN ('idea', 'post')"

    cur = conn.execute(
        f"""
        SELECT t.kind, t.tag, COUNT(*) AS cnt
        FROM item_tags t
        JOIN items i ON i.id = t.item_id
        {cat_filter}
        GROUP BY t.kind, t.tag
        ORDER BY cnt DESC, t.tag ASC
        LIMIT 60
        """
    )
    return [{"kind": r[0], "tag": r[1], "count": int(r[2])} for r in cur.fetchall()]


def create_original_message(
    conn: Any,
    *,
    topic_slug: str,
    raw_text: str,
    tg_topic_id: int | None = None,
    tg_message_id: int | None = None,
    source_url: str | None = None,
    source_type: str = "manual",
    author: str | None = None,
    extracted_text: str | None = None,
) -> dict[str, Any]:
    """Сохраняет оригинальное сообщение пользователя в архив оригиналов."""
    valid_slugs = ("movies", "books", "video", "article", "ideas")
    slug = topic_slug if topic_slug in valid_slugs else "ideas"
    cur = conn.execute(
        """
        INSERT INTO original_messages (
            topic_slug, tg_topic_id, tg_message_id,
            raw_text, source_url, source_type, author, extracted_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (slug, tg_topic_id, tg_message_id, raw_text, source_url, source_type, author, extracted_text),
    )
    row_id = int(cur.lastrowid)
    conn.commit()
    row = conn.execute(
        """
        SELECT id, topic_slug, tg_topic_id, tg_message_id, raw_text,
               source_url, source_type, author, extracted_text, created_at
        FROM original_messages WHERE id = ?
        """,
        (row_id,),
    ).fetchone()
    return {
        "id": row[0],
        "topic_slug": row[1],
        "tg_topic_id": row[2],
        "tg_message_id": row[3],
        "raw_text": row[4],
        "source_url": row[5],
        "source_type": row[6],
        "author": row[7],
        "extracted_text": row[8],
        "created_at": row[9],
    }


def list_original_messages(
    conn: Any,
    *,
    tab: str | None = None,
    q: str | None = None,
    limit: int = 300,
) -> list[dict[str, Any]]:
    """Возвращает архив оригинальных сообщений с фильтрацией по категории чата и простым поиском."""
    where_clauses: list[str] = []
    params: list[Any] = []

    if tab in ("movies", "books", "video", "article", "ideas"):
        where_clauses.append("topic_slug = ?")
        params.append(tab)

    if q and q.strip():
        raw_like = f"%{q.strip()}%"
        low_like = f"%{q.strip().lower()}%"
        where_clauses.append(
            "(raw_text LIKE ? OR LOWER(raw_text) LIKE ? "
            "OR COALESCE(extracted_text, '') LIKE ? OR LOWER(COALESCE(extracted_text, '')) LIKE ? "
            "OR COALESCE(author, '') LIKE ? OR COALESCE(source_url, '') LIKE ?)"
        )
        params.extend([raw_like, low_like, raw_like, low_like, raw_like, raw_like])

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    cur = conn.execute(
        f"""
        SELECT id, topic_slug, tg_topic_id, tg_message_id, raw_text,
               source_url, source_type, author, extracted_text, created_at
        FROM original_messages
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (*params, limit),
    )
    return [
        {
            "id": r[0],
            "topic_slug": r[1],
            "tg_topic_id": r[2],
            "tg_message_id": r[3],
            "raw_text": r[4],
            "source_url": r[5],
            "source_type": r[6],
            "author": r[7],
            "extracted_text": r[8],
            "created_at": r[9],
        }
        for r in cur.fetchall()
    ]


def delete_original_message(conn: Any, orig_id: int) -> dict[str, Any] | None:
    """Удаляет запись из архива оригинальных сообщений и все связанные с ней посты из каталога."""
    row = conn.execute(
        """
        SELECT id, topic_slug, tg_topic_id, tg_message_id, raw_text, source_url
        FROM original_messages WHERE id = ?
        """,
        (orig_id,),
    ).fetchone()
    if not row:
        return None

    orig_tg_msg_id = row[3]
    raw_text = (row[4] or "").strip()
    source_url = (row[5] or "").strip() or None

    matched_ids: set[int] = set()
    if source_url:
        for r in conn.execute("SELECT id FROM items WHERE canonical_url = ?", (source_url,)).fetchall():
            matched_ids.add(int(r[0]))
        for r in conn.execute("SELECT item_id FROM item_sources WHERE source_url = ?", (source_url,)).fetchall():
            matched_ids.add(int(r[0]))
        if raw_text and raw_text != source_url:
            for r in conn.execute("SELECT id FROM items WHERE canonical_url = ?", (raw_text,)).fetchall():
                matched_ids.add(int(r[0]))
            for r in conn.execute("SELECT item_id FROM item_sources WHERE source_url = ?", (raw_text,)).fetchall():
                matched_ids.add(int(r[0]))

    if raw_text:
        for r in conn.execute("SELECT id FROM items WHERE raw_input = ?", (raw_text,)).fetchall():
            matched_ids.add(int(r[0]))
        for r in conn.execute("SELECT item_id FROM item_sources WHERE raw_text = ?", (raw_text,)).fetchall():
            matched_ids.add(int(r[0]))

    if orig_tg_msg_id:
        for r in conn.execute("SELECT id FROM items WHERE tg_message_id = ?", (orig_tg_msg_id,)).fetchall():
            matched_ids.add(int(r[0]))

    deleted_items: list[dict[str, Any]] = []
    for item_id in matched_ids:
        it = get_item(conn, item_id)
        if it:
            deleted_items.append(it)
            conn.execute("DELETE FROM items_fts WHERE rowid = ?", (item_id,))
            conn.execute("DELETE FROM items WHERE id = ?", (item_id,))

    conn.execute("DELETE FROM original_messages WHERE id = ?", (orig_id,))
    conn.commit()
    return {
        "id": orig_id,
        "tg_message_id": orig_tg_msg_id,
        "deleted_items": deleted_items,
    }


def bulk_update_items(
    conn: Any,
    item_ids: list[int],
    *,
    status: str | None = None,
    add_tag: str | None = None,
    delete: bool = False,
) -> dict[str, Any]:
    """Массовое изменение статуса, добавление тега или удаление до 200 записей за один запрос."""
    normalized: set[int] = set()
    for raw in item_ids or []:
        try:
            val = int(raw)
        except (TypeError, ValueError):
            continue
        if val > 0:
            normalized.add(val)
    ids = sorted(normalized)[:200]
    if not ids:
        return {"action": "noop", "affected": 0, "ids": []}

    placeholders = ", ".join("?" for _ in ids)

    if delete:
        conn.execute(f"DELETE FROM items_fts WHERE rowid IN ({placeholders})", ids)
        conn.execute(f"DELETE FROM item_tags WHERE item_id IN ({placeholders})", ids)
        conn.execute(f"DELETE FROM item_sources WHERE item_id IN ({placeholders})", ids)
        cur = conn.execute(f"DELETE FROM items WHERE id IN ({placeholders})", ids)
        conn.commit()
        return {"action": "delete", "affected": int(cur.rowcount or 0), "ids": ids}

    if status is not None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        cur = conn.execute(
            f"UPDATE items SET status = ? WHERE id IN ({placeholders})",
            (status, *ids),
        )
        conn.commit()
        return {"action": "status", "status": status, "affected": int(cur.rowcount or 0), "ids": ids}

    if add_tag is not None:
        clean_tag = str(add_tag).strip().lstrip("#").lower()
        if not clean_tag:
            raise ValueError("Empty tag")
        valid_rows = conn.execute(f"SELECT id FROM items WHERE id IN ({placeholders})", ids).fetchall()
        valid_ids = [int(r[0]) for r in valid_rows]
        for iid in valid_ids:
            conn.execute(
                "INSERT OR IGNORE INTO item_tags (item_id, kind, tag) VALUES (?, 'tag', ?)",
                (iid, clean_tag),
            )
        conn.commit()
        for iid in valid_ids:
            sync_item_fts(conn, iid)
        return {"action": "add_tag", "tag": clean_tag, "affected": len(valid_ids), "ids": valid_ids}

    raise ValueError("No bulk action specified")


def get_catalog_stats(conn: Any, *, year: int | None = None) -> dict[str, Any]:
    """Возвращает агрегированную статистику, гистограмму оценок, активность по месяцам и дневник."""
    years_cur = conn.execute(
        "SELECT DISTINCT substr(created_at, 1, 4) FROM items "
        "WHERE created_at IS NOT NULL AND length(created_at) >= 4 ORDER BY 1 DESC"
    )
    available_years = sorted(
        {int(r[0]) for r in years_cur.fetchall() if r[0] and str(r[0]).isdigit()},
        reverse=True,
    )

    year_str = str(year) if year is not None else None
    where_created = "WHERE substr(created_at, 1, 4) = ?" if year_str else ""
    params: list[Any] = [year_str] if year_str else []

    row_sum = conn.execute(
        f"""
        SELECT
            COUNT(*),
            COALESCE(SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN status = 'planned' THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN status = 'inbox' THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN status = 'dropped' THEN 1 ELSE 0 END), 0),
            COUNT(user_rating),
            ROUND(AVG(user_rating), 2),
            COALESCE(SUM(CASE WHEN meta LIKE '%"user_note"%' THEN 1 ELSE 0 END), 0)
        FROM items
        {where_created}
        """,
        params,
    ).fetchone()

    summary = {
        "total": int(row_sum[0] or 0),
        "done": int(row_sum[1] or 0),
        "in_progress": int(row_sum[2] or 0),
        "planned": int(row_sum[3] or 0),
        "inbox": int(row_sum[4] or 0),
        "dropped": int(row_sum[5] or 0),
        "rated_count": int(row_sum[6] or 0),
        "avg_user_rating": float(row_sum[7]) if row_sum[7] is not None else None,
        "noted_count": int(row_sum[8] or 0),
    }

    cat_rows = conn.execute(
        f"""
        SELECT
            category,
            COUNT(*),
            COALESCE(SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(user_rating), 0),
            COUNT(user_rating)
        FROM items
        {where_created}
        GROUP BY category
        """,
        params,
    ).fetchall()
    cat_agg: dict[str, tuple[int, int, float, int]] = {
        str(r[0]): (int(r[1] or 0), int(r[2] or 0), float(r[3] or 0.0), int(r[4] or 0))
        for r in cat_rows
        if r[0]
    }
    buckets = (
        ("movies", "Кино и сериалы", ("movie", "series")),
        ("books", "Книги", ("book",)),
        ("video", "YouTube", ("video",)),
        ("article", "Статьи", ("article",)),
        ("ideas", "Идеи и посты", ("idea", "post")),
    )
    by_category: list[dict[str, Any]] = []
    for tab_key, label, cats in buckets:
        tot = sum(cat_agg.get(c, (0, 0, 0.0, 0))[0] for c in cats)
        dn = sum(cat_agg.get(c, (0, 0, 0.0, 0))[1] for c in cats)
        r_sum = sum(cat_agg.get(c, (0, 0, 0.0, 0))[2] for c in cats)
        r_cnt = sum(cat_agg.get(c, (0, 0, 0.0, 0))[3] for c in cats)
        by_category.append(
            {
                "tab": tab_key,
                "label": label,
                "total": tot,
                "done": dn,
                "avg_rating": round(r_sum / r_cnt, 2) if r_cnt else None,
            }
        )

    where_rated = "WHERE user_rating BETWEEN 1 AND 10" + (" AND substr(created_at, 1, 4) = ?" if year_str else "")
    rating_rows = conn.execute(
        f"SELECT user_rating, COUNT(*) FROM items {where_rated} GROUP BY user_rating",
        params,
    ).fetchall()
    rating_map = {int(r[0]): int(r[1]) for r in rating_rows if r[0] is not None}
    ratings_distribution = [{"rating": r, "count": rating_map.get(r, 0)} for r in range(1, 11)]

    where_i_created = "WHERE substr(i.created_at, 1, 4) = ?" if year_str else ""
    top_tags_rows = conn.execute(
        f"""
        SELECT t.tag, COUNT(*) AS cnt
        FROM item_tags t
        JOIN items i ON i.id = t.item_id
        {where_i_created}
        GROUP BY t.tag
        ORDER BY cnt DESC, t.tag ASC
        LIMIT 8
        """,
        params,
    ).fetchall()
    top_tags = [{"tag": str(r[0]), "count": int(r[1])} for r in top_tags_rows]

    where_m = "WHERE created_at IS NOT NULL AND length(created_at) >= 7" + (
        " AND substr(created_at, 1, 4) = ?" if year_str else ""
    )
    monthly_rows = conn.execute(
        f"""
        SELECT
            substr(created_at, 1, 7) AS ym,
            COUNT(*) AS added,
            COALESCE(SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END), 0) AS done
        FROM items
        {where_m}
        GROUP BY ym
        ORDER BY ym ASC
        """,
        params,
    ).fetchall()
    monthly_map = {str(r[0]): {"added": int(r[1] or 0), "done": int(r[2] or 0)} for r in monthly_rows if r[0]}
    if year is not None:
        monthly = [
            {
                "month": f"{year}-{m:02d}",
                "added": monthly_map.get(f"{year}-{m:02d}", {}).get("added", 0),
                "done": monthly_map.get(f"{year}-{m:02d}", {}).get("done", 0),
            }
            for m in range(1, 13)
        ]
    else:
        sorted_months = sorted(monthly_map.keys())[-12:]
        monthly = [
            {"month": ym, "added": monthly_map[ym]["added"], "done": monthly_map[ym]["done"]}
            for ym in sorted_months
        ]

    where_diary = "WHERE (status = 'done' OR user_rating IS NOT NULL)" + (
        " AND substr(COALESCE(updated_at, created_at), 1, 4) = ?" if year_str else ""
    )
    diary_rows = conn.execute(
        f"""
        SELECT
            id, category, status, title_ru, release_year, creator, poster_url,
            user_rating, rating_imdb, rating_kp, COALESCE(updated_at, created_at) AS activity_date
        FROM items
        {where_diary}
        ORDER BY activity_date DESC, id DESC
        LIMIT 30
        """,
        params,
    ).fetchall()
    diary = [
        {
            "id": int(r[0]),
            "category": r[1],
            "status": r[2],
            "title_ru": r[3],
            "release_year": r[4],
            "creator": r[5],
            "poster_url": r[6],
            "user_rating": r[7],
            "rating_imdb": r[8],
            "rating_kp": r[9],
            "activity_date": r[10],
        }
        for r in diary_rows
    ]

    return {
        "year": year,
        "available_years": available_years,
        "summary": summary,
        "by_category": by_category,
        "ratings_distribution": ratings_distribution,
        "top_tags": top_tags,
        "monthly": monthly,
        "diary": diary,
    }
