from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import repo
from app.db.client import get_connection
from app.db.migrate import apply_migrations
from mcp_server.server import mcp_get_item, mcp_list_items, mcp_run_select, mcp_search_items
from scripts.backup import create_sql_backup


class TestStage7MCPAndBackup(unittest.TestCase):
    def test_mcp_read_only_tools(self) -> None:
        conn = get_connection(":memory:")
        apply_migrations(conn)

        created = repo.create_item(
            conn,
            category="book",
            title_ru="Гиперион",
            creator="Дэн Симмонс",
            rating_kp=8.56,
            rating_imdb=4.28,
            genres=["фантастика"],
        )

        found = mcp_search_items("Гиперион", conn=conn)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["id"], created["id"])

        detail = mcp_get_item(created["id"], conn=conn)
        assert detail is not None
        self.assertEqual(detail["creator"], "Дэн Симмонс")

        rows = mcp_run_select("SELECT id, title_ru FROM items", conn=conn)
        self.assertEqual(rows, [{"id": created["id"], "title_ru": "Гиперион"}])

        # Запрет любых пишущих SQL-запросов
        with self.assertRaises(ValueError):
            mcp_run_select("DELETE FROM items", conn=conn)
        with self.assertRaises(ValueError):
            mcp_run_select("SELECT * FROM items; DROP TABLE items", conn=conn)

    def test_sql_backup_creation(self) -> None:
        conn = get_connection(":memory:")
        apply_migrations(conn)
        conn.close()
        backup_path = create_sql_backup(db_path_override="data/second_brain.db")
        self.assertTrue(backup_path.is_file())
        content = backup_path.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
