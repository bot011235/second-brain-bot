"""Запуск миграций БД вручную: python scripts/migrate.py"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db.migrate import apply_migrations  # noqa: E402

if __name__ == "__main__":
    applied = apply_migrations()
    print(f"Применены миграции: {applied}" if applied else "Все миграции уже применены.")
