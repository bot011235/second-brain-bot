"""Генерирует чистый ZIP-архив проекта (без .env, .git, __pycache__) для загрузки в Google Cloud Shell."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
OUT_ZIP = ROOT / "cloud_run_bundle.zip"

INCLUDE_PATHS = [
    "Dockerfile",
    ".dockerignore",
    "pyproject.toml",
    "app",
    "scripts",
]


def build_bundle() -> None:
    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE_PATHS:
            p = ROOT / rel
            if p.is_file():
                zf.write(p, arcname=rel)
            elif p.is_dir():
                for sub in sorted(p.rglob("*")):
                    if sub.is_file() and "__pycache__" not in sub.parts and not sub.name.endswith(".pyc"):
                        zf.write(sub, arcname=str(sub.relative_to(ROOT)).replace("\\", "/"))
    print(f"✅ Архив для Google Cloud Run создан: {OUT_ZIP} ({OUT_ZIP.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build_bundle()
