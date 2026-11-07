"""Ежедневный бэкап базы данных в SQL-дамп с ротацией (7 последних дампов).

Запуск:
    python scripts/backup.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db.client import get_connection  # noqa: E402

BACKUPS_DIR = Path(__file__).resolve().parent.parent / "backups"


def create_sql_backup(keep_last: int = 7, db_path_override: str | None = None) -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUPS_DIR / f"second_brain_{ts}.sql"

    conn = get_connection(db_path_override)
    try:
        if hasattr(conn, "iterdump"):
            dump_lines = list(conn.iterdump())
            backup_file.write_text("\n".join(dump_lines), encoding="utf-8")
        else:
            # Резервный экспорт для libsql remote
            tables = ["items", "item_sources", "item_tags", "bot_state"]
            out_lines = ["-- libSQL logical dump"]
            for tbl in tables:
                cur = conn.execute(f"SELECT * FROM {tbl}")
                rows = cur.fetchall()
                for row in rows:
                    vals = ", ".join("NULL" if v is None else repr(v) for v in row)
                    out_lines.append(f"INSERT INTO {tbl} VALUES ({vals});")
            backup_file.write_text("\n".join(out_lines), encoding="utf-8")
    finally:
        conn.close()

    # Ротация старых бэкапов
    all_backups = sorted(BACKUPS_DIR.glob("second_brain_*.sql"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old_file in all_backups[keep_last:]:
        try:
            old_file.unlink()
        except OSError:
            pass

    return backup_file


if __name__ == "__main__":
    path = create_sql_backup()
    print(f"Бэкап создан: {path}")
