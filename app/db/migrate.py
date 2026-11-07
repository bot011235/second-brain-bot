from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db.client import get_connection

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def apply_migrations(conn: Any | None = None) -> list[str]:
    """Применяет все неприменённые SQL-миграции по порядку и возвращает список применённых файлов."""
    own_conn = conn is None
    if conn is None:
        conn = get_connection()

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     TEXT PRIMARY KEY,
                applied_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()

        cur = conn.execute("SELECT version FROM schema_migrations")
        applied = {row[0] for row in cur.fetchall()}

        newly_applied: list[str] = []
        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = sql_file.name
            if version in applied:
                continue
            sql_script = sql_file.read_text(encoding="utf-8")
            conn.executescript(sql_script)
            conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
            conn.commit()
            newly_applied.append(version)

        return newly_applied
    finally:
        if own_conn:
            conn.close()
