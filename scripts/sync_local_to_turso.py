from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import settings
from app.db.client import get_connection
from app.db.migrate import apply_migrations
from app.db.repo import ITEM_COLUMNS, sync_item_fts


def sync_local_to_turso() -> None:
    if not (settings.turso_database_url and settings.turso_auth_token):
        print("❌ Ошибка: В .env не заданы TURSO_DATABASE_URL и TURSO_AUTH_TOKEN.")
        sys.exit(1)

    local_path = Path(settings.local_db_path)
    if not local_path.exists():
        print(f"ℹ️ Локальная база {local_path} не найдена, применяю только миграции в Turso...")
        apply_migrations()
        print("✅ Схема в Turso готова!")
        return

    print("1️⃣ Применяю схему миграций в Turso...")
    applied = apply_migrations()
    print(f"   Применены миграции: {applied or 'уже актуальны'}")

    local_conn = sqlite3.connect(str(local_path))
    remote_conn = get_connection()

    try:
        cols_str = ", ".join(ITEM_COLUMNS)
        placeholders = ", ".join("?" for _ in ITEM_COLUMNS)
        items = local_conn.execute(f"SELECT {cols_str} FROM items ORDER BY id").fetchall()
        print(f"2️⃣ Переношу карточки (items): {len(items)} шт...")
        for row in items:
            remote_conn.execute(
                f"INSERT OR REPLACE INTO items ({cols_str}) VALUES ({placeholders})",
                row,
            )

        sources = local_conn.execute(
            "SELECT id, item_id, source_url, source_type, raw_text, added_at FROM item_sources ORDER BY id"
        ).fetchall()
        print(f"3️⃣ Переношу источники (item_sources): {len(sources)} шт...")
        for row in sources:
            remote_conn.execute(
                "INSERT OR REPLACE INTO item_sources (id, item_id, source_url, source_type, raw_text, added_at) VALUES (?, ?, ?, ?, ?, ?)",
                row,
            )

        tags = local_conn.execute(
            "SELECT item_id, kind, tag FROM item_tags"
        ).fetchall()
        print(f"4️⃣ Переношу жанры и теги (item_tags): {len(tags)} шт...")
        for row in tags:
            remote_conn.execute(
                "INSERT OR IGNORE INTO item_tags (item_id, kind, tag) VALUES (?, ?, ?)",
                row,
            )

        print("5️⃣ Индексирую полнотекстовый поиск FTS5 в Turso...")
        for row in items:
            sync_item_fts(remote_conn, int(row[0]))

        remote_conn.commit()
        print(f"✅ Успешно! Все {len(items)} карточек синхронизированы с облаком Turso.")
    finally:
        local_conn.close()
        remote_conn.close()


if __name__ == "__main__":
    sync_local_to_turso()
