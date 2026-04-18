"""SQLite-backed store for user-authored personas."""
from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_personas (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    soul_md     TEXT NOT NULL DEFAULT '',
    agent_md    TEXT NOT NULL DEFAULT '',
    created_at  INTEGER NOT NULL
);
"""


class UserPersonaStore:
    def __init__(self, db_path: Path):
        self._db = Path(db_path)
        self._db.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            con.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._db)
        con.row_factory = sqlite3.Row
        return con

    def create(
        self,
        *,
        name: str,
        soul_md: str,
        agent_md: str = "",
        description: str | None = None,
    ) -> str:
        pid = uuid.uuid4().hex
        with self._conn() as con:
            con.execute(
                "INSERT INTO user_personas (id, name, description, soul_md, agent_md, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pid, name, description, soul_md, agent_md, int(time.time())),
            )
        return pid

    def get(self, pid: str) -> dict[str, Any] | None:
        with self._conn() as con:
            row = con.execute(
                "SELECT id, name, description, soul_md, agent_md, created_at "
                "FROM user_personas WHERE id = ?",
                (pid,),
            ).fetchone()
        return dict(row) if row else None

    def list(self) -> list[dict[str, Any]]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT id, name, description, soul_md, agent_md, created_at "
                "FROM user_personas ORDER BY created_at DESC, rowid DESC",
            ).fetchall()
        return [dict(r) for r in rows]

    def update(self, pid: str, **fields) -> None:
        allowed = {"name", "description", "soul_md", "agent_md"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"unknown fields: {sorted(bad)}")
        if not fields:
            return
        assignments = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [pid]
        with self._conn() as con:
            con.execute(f"UPDATE user_personas SET {assignments} WHERE id = ?", values)

    def delete(self, pid: str) -> None:
        with self._conn() as con:
            con.execute("DELETE FROM user_personas WHERE id = ?", (pid,))
