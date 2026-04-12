"""Lightweight browsing history for platform apps (Reddit, X, etc.).

NOT a KnowledgeItem — no ingest, no embedding, no monitoring.
Just a breadcrumb trail of recently viewed content for quick recovery.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS browsing_history (
    url TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    preview TEXT NOT NULL DEFAULT '',
    extra_json TEXT NOT NULL DEFAULT '{}',
    viewed_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_source ON browsing_history(source_type);
CREATE INDEX IF NOT EXISTS idx_history_viewed ON browsing_history(viewed_at DESC);
"""

DEFAULT_RETENTION_DAYS = 30


class BrowsingHistoryStore:
    def __init__(self, db_path: str | Path = "data/browsing-history.db"):
        self._db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    async def init(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    async def record(
        self,
        url: str,
        source_type: str,
        title: str = "",
        author: str = "",
        preview: str = "",
        extra_json: str = "{}",
    ) -> None:
        """Upsert a viewed item. Updates viewed_at if already exists."""
        now = time.time()
        self._conn.execute(
            """INSERT INTO browsing_history (url, source_type, title, author, preview, extra_json, viewed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(url) DO UPDATE SET
                 title = excluded.title,
                 author = excluded.author,
                 preview = excluded.preview,
                 extra_json = excluded.extra_json,
                 viewed_at = excluded.viewed_at""",
            (url, source_type, title, author, preview[:200], extra_json, now),
        )
        self._conn.commit()

    async def list_recent(
        self,
        source_type: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List recently viewed items, newest first."""
        if source_type:
            rows = self._conn.execute(
                "SELECT * FROM browsing_history WHERE source_type = ? ORDER BY viewed_at DESC LIMIT ?",
                (source_type, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM browsing_history ORDER BY viewed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    async def clear(self, source_type: str | None = None) -> int:
        """Clear history. Returns count of deleted rows."""
        if source_type:
            cursor = self._conn.execute(
                "DELETE FROM browsing_history WHERE source_type = ?",
                (source_type,),
            )
        else:
            cursor = self._conn.execute("DELETE FROM browsing_history")
        self._conn.commit()
        return cursor.rowcount

    async def prune(self, retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
        """Remove entries older than retention_days. Returns count deleted."""
        cutoff = time.time() - (retention_days * 86400)
        cursor = self._conn.execute(
            "DELETE FROM browsing_history WHERE viewed_at < ?",
            (cutoff,),
        )
        self._conn.commit()
        return cursor.rowcount
