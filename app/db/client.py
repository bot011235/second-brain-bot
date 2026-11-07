from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

_STMT_SPLIT_RE = re.compile(
    r";\s*(?=(?:[^']*'[^']*')*[^']*$)(?!\s*END\b)",
    flags=re.IGNORECASE,
)


def _split_sql_script(script: str) -> list[str]:
    """Разбивает SQL-скрипт на отдельные выражения с учётом триггеров BEGIN ... END;."""
    cleaned_lines = [
        line for line in script.splitlines() if not line.strip().startswith("--")
    ]
    cleaned = "\n".join(cleaned_lines)
    stmts: list[str] = []
    buffer: list[str] = []
    in_trigger = False

    for line in cleaned.splitlines():
        stripped = line.strip().upper()
        if stripped.startswith("CREATE TRIGGER"):
            in_trigger = True
        buffer.append(line)
        if in_trigger:
            if stripped.startswith("END;") or stripped == "END":
                stmt = "\n".join(buffer).strip()
                if not stmt.endswith(";"):
                    stmt += ";"
                stmts.append(stmt)
                buffer = []
                in_trigger = False
        else:
            if stripped.endswith(";"):
                stmt = "\n".join(buffer).strip()
                if stmt and stmt != ";":
                    stmts.append(stmt)
                buffer = []

    tail = "\n".join(buffer).strip()
    if tail and tail != ";":
        stmts.append(tail)
    return stmts


def _to_hrana_arg(val: Any) -> dict[str, Any]:
    if val is None:
        return {"type": "null"}
    if isinstance(val, bool):
        return {"type": "integer", "value": "1" if val else "0"}
    if isinstance(val, int):
        return {"type": "integer", "value": str(val)}
    if isinstance(val, float):
        return {"type": "float", "value": val}
    if isinstance(val, (bytes, bytearray)):
        import base64

        return {"type": "blob", "base64": base64.b64encode(bytes(val)).decode("ascii")}
    return {"type": "text", "value": str(val)}


def _from_hrana_cell(cell: dict[str, Any]) -> Any:
    ctype = cell.get("type")
    if ctype == "null" or ctype is None:
        return None
    if ctype == "integer":
        return int(cell["value"])
    if ctype == "float":
        return float(cell["value"])
    if ctype == "blob":
        import base64

        return base64.b64decode(cell.get("base64", ""))
    return cell.get("value")


class TursoHttpCursor:
    """sqlite3-совместимый курсор поверх Turso HTTP Pipeline API (v2/pipeline)."""

    def __init__(
        self,
        rows: list[tuple[Any, ...]],
        lastrowid: int | None = None,
        rowcount: int = 0,
    ) -> None:
        self._rows = rows
        self._idx = 0
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchone(self) -> tuple[Any, ...] | None:
        if self._idx >= len(self._rows):
            return None
        row = self._rows[self._idx]
        self._idx += 1
        return row

    def fetchall(self) -> list[tuple[Any, ...]]:
        if self._idx == 0:
            self._idx = len(self._rows)
            return list(self._rows)
        rest = self._rows[self._idx :]
        self._idx = len(self._rows)
        return list(rest)


class TursoHttpConnection:
    """Чистый HTTP-клиент к Turso (libSQL Hrana v2 pipeline), не требующий компиляции Rust/C пакетов."""

    def __init__(self, database_url: str, auth_token: str) -> None:
        url = database_url.strip()
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://") :]
        elif url.startswith("wss://"):
            url = "https://" + url[len("wss://") :]
        self.pipeline_url = url.rstrip("/") + "/v2/pipeline"
        self.headers = {
            "Authorization": f"Bearer {auth_token.strip()}",
            "Content-Type": "application/json",
        }
        self._client = httpx.Client(timeout=20.0, headers=self.headers)

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> TursoHttpCursor:
        stmt: dict[str, Any] = {"sql": sql}
        if params:
            stmt["args"] = [_to_hrana_arg(p) for p in params]

        payload = {
            "requests": [
                {"type": "execute", "stmt": stmt},
                {"type": "close"},
            ]
        }
        resp = self._client.post(self.pipeline_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        first = data.get("results", [{}])[0]
        if first.get("type") == "error":
            err_msg = first.get("error", {}).get("message", "Turso SQL error")
            raise RuntimeError(f"Turso error: {err_msg} (SQL: {sql[:120]})")

        res = first.get("response", {}).get("result", {})
        raw_rows = res.get("rows", [])
        rows = [tuple(_from_hrana_cell(c) for c in r) for r in raw_rows]
        last_id_raw = res.get("last_insert_rowid")
        lastrowid = int(last_id_raw) if last_id_raw is not None else None
        rowcount = int(res.get("affected_row_count", 0))
        return TursoHttpCursor(rows=rows, lastrowid=lastrowid, rowcount=rowcount)

    def executescript(self, sql_script: str) -> None:
        statements = _split_sql_script(sql_script)
        if not statements:
            return
        requests: list[dict[str, Any]] = [
            {"type": "execute", "stmt": {"sql": s}} for s in statements
        ]
        requests.append({"type": "close"})
        resp = self._client.post(self.pipeline_url, json={"requests": requests})
        resp.raise_for_status()
        data = resp.json()
        for idx, item in enumerate(data.get("results", [])):
            if item.get("type") == "error":
                err_msg = item.get("error", {}).get("message", "Turso script error")
                raise RuntimeError(f"Turso script error at stmt #{idx + 1}: {err_msg}")

    def commit(self) -> None:
        # HTTP pipeline выполняет каждый запрос в авто-коммите
        pass

    def close(self) -> None:
        self._client.close()


def get_connection(db_path_override: str | None = None) -> Any:
    """Возвращает подключение к Turso (libSQL / HTTP API) или к локальному файлу SQLite."""
    if db_path_override:
        if db_path_override != ":memory:":
            Path(db_path_override).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path_override)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    if settings.turso_database_url and settings.turso_auth_token:
        try:
            import libsql_experimental as libsql  # type: ignore[import-not-found]

            conn = libsql.connect(
                database=settings.turso_database_url,
                auth_token=settings.turso_auth_token,
            )
            conn.execute("PRAGMA foreign_keys = ON;")
            return conn
        except ImportError:
            return TursoHttpConnection(
                database_url=settings.turso_database_url,
                auth_token=settings.turso_auth_token,
            )

    local_path = Path(settings.local_db_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(local_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
