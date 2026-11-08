from __future__ import annotations

import json
from typing import Any

from app.utils.normalize import normalize_text

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
        "SELECT title_ru, title_orig, creator, summary FROM items WHERE id = ?",
        (item_id,),
    )
    row = cur.fetchone()
    if row is None:
        conn.commit()
        return

    title_ru, title_orig, creator, summary = row
    tags_cur = conn.execute("SELECT tag FROM item_tags WHERE item_id = ?", (item_id,))
    tags_str = " ".join(r[0] for r in tags_cur.fetchall() if r[0])

    sources_cur = conn.execute("SELECT raw_text FROM item_sources WHERE item_id = ?", (item_id,))
    sources_str = " ".join(r[0] for r in sources_cur.fetchall() if r[0])

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
    rating_imdb: float | None = None,
    rating_kp: float | None = None,
    rating_rt: int | None = None,
    url_rt: str | None = None,
    genres: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    processing_status: str = "ok",
) -> dict[str, Any] | None:
    norm_title = normalize_text(title_ru or title_orig or "") or "untitled"
    norm_creator = normalize_text(creator) if creator else None
    meta_json = json.dumps(meta, ensure_ascii=False) if meta else None

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
            imdb_id,
            kp_id,
            google_books_id,
            isbn13,
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
    set_item_tags(conn, item_id, genres=genres, commit=False)
    conn.commit()
    sync_item_fts(conn, item_id)
    return get_item(conn, item_id)


def get_item(conn: Any, item_id: int) -> dict[str, Any] | None:
    cols = ", ".join(ITEM_COLUMNS)
    cur = conn.execute(f"SELECT {cols} FROM items WHERE id = ?", (item_id,))
    item = _row_to_item(cur.fetchone())
    if item is None:
        return None

    tags_cur = conn.execute("SELECT kind, tag FROM item_tags WHERE item_id = ? ORDER BY tag", (item_id,))
    item["genres"] = [r[1] for r in tags_cur.fetchall() if r[0] == "genre"]
    tags_cur = conn.execute("SELECT tag FROM item_tags WHERE item_id = ? AND kind = 'tag' ORDER BY tag", (item_id,))
    item["tags"] = [r[0] for r in tags_cur.fetchall()]

    src_cur = conn.execute(
        "SELECT id, source_url, source_type, raw_text, added_at FROM item_sources WHERE item_id = ? ORDER BY id",
        (item_id,),
    )
    item["sources"] = [
        {"id": r[0], "source_url": r[1], "source_type": r[2], "raw_text": r[3], "added_at": r[4]}
        for r in src_cur.fetchall()
    ]
    return item


def update_item_status(conn: Any, item_id: int, status: str) -> dict[str, Any] | None:
    conn.execute("UPDATE items SET status = ? WHERE id = ?", (status, item_id))
    conn.commit()
    return get_item(conn, item_id)


def set_item_tg_message_id(conn: Any, item_id: int, tg_message_id: int) -> None:
    conn.execute("UPDATE items SET tg_message_id = ? WHERE id = ?", (tg_message_id, item_id))
    conn.commit()


def delete_item(conn: Any, item_id: int) -> bool:
    item = get_item(conn, item_id)
    conn.execute("DELETE FROM items_fts WHERE rowid = ?", (item_id,))
    cur = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    deleted = cur.rowcount > 0
    if deleted and item:
        urls: set[str] = set()
        if item.get("canonical_url"):
            urls.add(str(item["canonical_url"]))
        for s in item.get("sources") or []:
            if s.get("source_url"):
                urls.add(str(s["source_url"]))
        for u in urls:
            rem = conn.execute(
                "SELECT 1 FROM items WHERE canonical_url = ? "
                "UNION SELECT 1 FROM item_sources WHERE source_url = ? LIMIT 1",
                (u, u),
            ).fetchone()
            if not rem:
                try:
                    conn.execute("DELETE FROM original_messages WHERE source_url = ?", (u,))
                except Exception:
                    pass
        raw_in = (item.get("raw_input") or "").strip()
        if raw_in:
            rem_raw = conn.execute("SELECT 1 FROM items WHERE raw_input = ? LIMIT 1", (raw_in,)).fetchone()
            if not rem_raw:
                try:
                    conn.execute(
                        "DELETE FROM original_messages WHERE raw_text = ? AND source_url IS NULL",
                        (raw_in,),
                    )
                except Exception:
                    pass
    conn.commit()
    return deleted


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
) -> dict[str, Any] | None:
    if status is not None:
        conn.execute("UPDATE items SET status = ? WHERE id = ?", (status, item_id))
    if user_rating is not None:
        val = None if user_rating == 0 else int(user_rating)
        conn.execute("UPDATE items SET user_rating = ? WHERE id = ?", (val, item_id))
    conn.commit()
    return get_item(conn, item_id)


def list_items_catalog(
    conn: Any,
    *,
    tab: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    sort: str = "created",
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Выборка элементов для витрины Telegram Mini App с фильтрацией, поиском и сортировкой."""
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

    if status and status != "all":
        where_clauses.append("i.status = ?")
        params.append(status)

    if tag:
        where_clauses.append("EXISTS (SELECT 1 FROM item_tags t WHERE t.item_id = i.id AND t.tag = ?)")
        params.append(tag.strip().lower())

    if q and q.strip():
        norm_q = normalize_text(q)
        like_q = f"%{norm_q or q.strip().lower()}%"
        raw_like = f"%{q.strip()}%"
        where_clauses.append(
            "(i.normalized_title LIKE ? OR i.normalized_creator LIKE ? OR i.title_ru LIKE ? OR i.title_orig LIKE ? OR i.summary LIKE ?)"
        )
        params.extend([like_q, like_q, raw_like, raw_like, raw_like])

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    sort_map = {
        "created": "i.created_at DESC, i.id DESC",
        "imdb": "COALESCE(i.rating_imdb, -1) DESC, i.id DESC",
        "kp": "COALESCE(i.rating_kp, -1) DESC, i.id DESC",
        "rt": "COALESCE(i.rating_rt, -1) DESC, i.id DESC",
        "user": "COALESCE(i.user_rating, -1) DESC, i.id DESC",
    }
    order_sql = sort_map.get(sort, sort_map["created"])

    cur = conn.execute(f"SELECT i.id FROM items i {where_sql} ORDER BY {order_sql} LIMIT ?", (*params, limit))
    ids = [int(r[0]) for r in cur.fetchall()]
    out: list[dict[str, Any]] = []
    for item_id in ids:
        item = get_item(conn, item_id)
        if item:
            out.append(item)
    return out


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
