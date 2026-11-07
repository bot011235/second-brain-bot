"""Read-Only MCP сервер для подключения личной базы знаний («Второй мозг») к Google Antigravity, Claude Desktop, Cursor.

Поддерживает как FastMCP (если установлен пакет `mcp`), так и прямое использование функций из Python.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import repo  # noqa: E402
from app.db.client import get_connection  # noqa: E402

_FORBIDDEN_SQL_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH|PRAGMA)\b",
    flags=re.IGNORECASE,
)


def mcp_search_items(
    query: str,
    tab: str | None = None,
    status: str | None = None,
    limit: int = 20,
    conn: Any | None = None,
) -> list[dict[str, Any]]:
    """Полнотекстовый поиск по фильмам, сериалам, книгам, YouTube, статьям и идеям."""
    own = conn is None
    conn = conn or get_connection()
    try:
        return repo.list_items_catalog(conn, tab=tab, status=status, q=query, limit=min(limit, 100))
    finally:
        if own:
            conn.close()


def mcp_get_item(item_id: int, conn: Any | None = None) -> dict[str, Any] | None:
    """Возвращает полную карточку элемента вместе с жанрами, тегами и источниками."""
    own = conn is None
    conn = conn or get_connection()
    try:
        return repo.get_item(conn, int(item_id))
    finally:
        if own:
            conn.close()


def mcp_list_items(
    tab: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    sort: str = "created",
    limit: int = 50,
    conn: Any | None = None,
) -> list[dict[str, Any]]:
    """Список элементов с фильтрацией по вкладке, статусу, жанру/тегу и сортировкой по рейтингам."""
    own = conn is None
    conn = conn or get_connection()
    try:
        return repo.list_items_catalog(conn, tab=tab, status=status, tag=tag, sort=sort, limit=min(limit, 200))
    finally:
        if own:
            conn.close()


def mcp_run_select(sql: str, max_rows: int = 100, conn: Any | None = None) -> list[dict[str, Any]]:
    """Выполняет строго READ-ONLY SELECT-запрос к базе второго мозга."""
    cleaned = sql.strip().rstrip(";")
    if not cleaned.upper().startswith("SELECT") or _FORBIDDEN_SQL_RE.search(cleaned):
        raise ValueError("Разрешены только безопасные SELECT-запросы (read-only).")

    own = conn is None
    conn = conn or get_connection()
    try:
        cur = conn.execute(cleaned)
        col_names = [desc[0] for desc in (cur.description or [])]
        rows = cur.fetchmany(min(max_rows, 500))
        return [dict(zip(col_names, r)) for r in rows]
    finally:
        if own:
            conn.close()


def build_fastmcp_server() -> Any:
    from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

    mcp = FastMCP("PersonalSecondBrain")

    @mcp.tool()
    def search_items(query: str, tab: str | None = None, status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Поиск по личной базе фильмов, книг, видео, статей и заметок."""
        return mcp_search_items(query=query, tab=tab, status=status, limit=limit)

    @mcp.tool()
    def get_item(item_id: int) -> dict[str, Any] | None:
        """Получить полную карточку элемента по ID."""
        return mcp_get_item(item_id=item_id)

    @mcp.tool()
    def list_items(
        tab: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        sort: str = "created",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Фильтрация и сортировка каталога (tab: movies|books|video|article|ideas, sort: created|imdb|kp|rt|user)."""
        return mcp_list_items(tab=tab, status=status, tag=tag, sort=sort, limit=limit)

    @mcp.tool()
    def run_select(sql: str) -> list[dict[str, Any]]:
        """Выполнить read-only SQL SELECT запрос к таблицам items, item_sources, item_tags."""
        return mcp_run_select(sql=sql)

    return mcp


if __name__ == "__main__":
    server = build_fastmcp_server()
    server.run()
