"""Zero-Loss Archive Layer (taOSmd).

Append-only daily archive of every event in the system. Never modified, never
deleted, never summarised. The raw truth, kept indefinitely.

Events include: agent conversations, tool calls, API interactions, decisions,
errors, system state, and optionally user activity (browsing, reading, app usage).

Storage: data/archive/YYYY/MM/DD.jsonl (one JSON line per event, gzipped after day ends).
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Event types
EVENT_CONVERSATION = "conversation"       # Agent chat message (user or agent)
EVENT_TOOL_CALL = "tool_call"             # Agent tool invocation + result
EVENT_API_CALL = "api_call"               # External API request + response
EVENT_DECISION = "decision"               # Decision point with chosen path
EVENT_ERROR = "error"                     # Error with context and resolution
EVENT_SYSTEM = "system"                   # System state change (agent start/stop, etc.)
EVENT_APP_USAGE = "app_usage"             # User opened/closed/interacted with an app
EVENT_CONTENT_VIEW = "content_view"       # User viewed a post, page, thread, video
EVENT_SEARCH = "search"                   # User searched for something
EVENT_INGEST = "ingest"                   # Content ingested into knowledge base
EVENT_MONITOR = "monitor"                 # Monitoring event (poll, change detected)

ALL_EVENT_TYPES = [
    EVENT_CONVERSATION, EVENT_TOOL_CALL, EVENT_API_CALL, EVENT_DECISION,
    EVENT_ERROR, EVENT_SYSTEM, EVENT_APP_USAGE, EVENT_CONTENT_VIEW,
    EVENT_SEARCH, EVENT_INGEST, EVENT_MONITOR,
]

# User activity events are opt-in
USER_ACTIVITY_EVENTS = {EVENT_APP_USAGE, EVENT_CONTENT_VIEW, EVENT_SEARCH}

# Index schema for fast lookups (the JSONL files are the source of truth)
INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS archive_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL,
    agent_name TEXT,
    app_id TEXT,
    summary TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL,
    line_number INTEGER NOT NULL,
    data_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_archive_ts ON archive_index(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_archive_type ON archive_index(event_type);
CREATE INDEX IF NOT EXISTS idx_archive_agent ON archive_index(agent_name);
CREATE INDEX IF NOT EXISTS idx_archive_app ON archive_index(app_id);

CREATE TABLE IF NOT EXISTS archive_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS archive_fts USING fts5(
    summary,
    content,
    content_rowid='id',
    tokenize='porter unicode61'
);
"""


class ArchiveStore:
    """Append-only event archive with daily JSONL files and SQLite index."""

    def __init__(
        self,
        archive_dir: str | Path = "data/archive",
        index_path: str | Path = "data/archive-index.db",
    ):
        self._archive_dir = Path(archive_dir)
        self._index_path = str(index_path)
        self._conn: sqlite3.Connection | None = None
        self._current_file: Any = None
        self._current_date: str = ""
        self._user_tracking_enabled: bool = False

    async def init(self) -> None:
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        Path(self._index_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._index_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(INDEX_SCHEMA)
        self._conn.commit()
        # Load user tracking preference
        row = self._conn.execute(
            "SELECT value FROM archive_settings WHERE key = 'user_tracking_enabled'"
        ).fetchone()
        self._user_tracking_enabled = bool(row and row["value"] == "true")

    async def close(self) -> None:
        if self._current_file:
            self._current_file.close()
            self._current_file = None
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    @property
    def user_tracking_enabled(self) -> bool:
        return self._user_tracking_enabled

    async def set_user_tracking(self, enabled: bool) -> None:
        """Enable or disable user activity tracking (opt-in)."""
        self._user_tracking_enabled = enabled
        self._conn.execute(
            """INSERT INTO archive_settings (key, value) VALUES ('user_tracking_enabled', ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            ("true" if enabled else "false",),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def _get_daily_path(self, ts: float) -> Path:
        """Get the JSONL file path for a given timestamp."""
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return self._archive_dir / f"{dt.year}" / f"{dt.month:02d}" / f"{dt.day:02d}.jsonl"

    def _ensure_file(self, ts: float) -> tuple[Any, str]:
        """Ensure the daily JSONL file is open for writing."""
        path = self._get_daily_path(ts)
        date_str = path.stem
        parent = str(path.parent)
        if self._current_date != parent:
            if self._current_file:
                self._current_file.close()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._current_file = open(path, "a", encoding="utf-8")
            self._current_date = parent
        return self._current_file, str(path)

    async def record(
        self,
        event_type: str,
        data: dict,
        agent_name: str | None = None,
        app_id: str | None = None,
        summary: str = "",
    ) -> int:
        """Record an event to the archive. Returns the index row ID."""
        # Skip user activity events if tracking is disabled
        if event_type in USER_ACTIVITY_EVENTS and not self._user_tracking_enabled:
            return -1

        ts = time.time()
        event = {
            "timestamp": ts,
            "event_type": event_type,
            "agent_name": agent_name,
            "app_id": app_id,
            "summary": summary,
            "data": data,
        }

        # Write to JSONL
        f, file_path = self._ensure_file(ts)
        line = json.dumps(event, default=str)
        f.write(line + "\n")
        f.flush()

        # Count lines for line_number
        line_count = sum(1 for _ in open(file_path, "r", encoding="utf-8"))

        # Index for fast lookup
        cursor = self._conn.execute(
            """INSERT INTO archive_index
               (timestamp, event_type, agent_name, app_id, summary, file_path, line_number, data_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, event_type, agent_name, app_id, summary, file_path, line_count, json.dumps(data, default=str)),
        )

        # Index in FTS for full-text search
        row_id = cursor.lastrowid
        # Build searchable content from data fields
        content_parts = [summary]
        for key in ("content", "text", "msg", "query", "tool", "result", "error"):
            val = data.get(key)
            if val and isinstance(val, str):
                content_parts.append(val)
        content_text = " ".join(content_parts)
        if content_text.strip():
            self._conn.execute(
                "INSERT INTO archive_fts (rowid, summary, content) VALUES (?, ?, ?)",
                (row_id, summary, content_text),
            )

        self._conn.commit()
        return row_id

    # ------------------------------------------------------------------
    # Full-text search
    # ------------------------------------------------------------------

    async def search_fts(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text search across all archived content using FTS5.

        This is the key method for LongMemEval-style recall — it searches
        the raw verbatim text, not just extracted triples.
        """
        try:
            rows = self._conn.execute(
                """SELECT a.*, highlight(archive_fts, 1, '<b>', '</b>') as highlight
                   FROM archive_fts f
                   JOIN archive_index a ON a.id = f.rowid
                   WHERE archive_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (query, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            # Fallback to LIKE search if FTS query syntax fails
            return await self.query(search=query, limit=limit)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    async def query(
        self,
        event_type: str | None = None,
        agent_name: str | None = None,
        app_id: str | None = None,
        since: float | None = None,
        until: float | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Query the archive index with filters."""
        conditions = []
        params: list = []

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if agent_name:
            conditions.append("agent_name = ?")
            params.append(agent_name)
        if app_id:
            conditions.append("app_id = ?")
            params.append(app_id)
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)
        if until:
            conditions.append("timestamp <= ?")
            params.append(until)
        if search:
            conditions.append("(summary LIKE ? OR data_json LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])

        rows = self._conn.execute(
            f"SELECT * FROM archive_index {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    async def get_event(self, event_id: int) -> dict | None:
        """Get a single event by index ID, including full data from JSONL."""
        row = self._conn.execute(
            "SELECT * FROM archive_index WHERE id = ?", (event_id,)
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        # Parse stored data_json
        try:
            result["data"] = json.loads(result.get("data_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            result["data"] = {}
        return result

    async def count(
        self,
        event_type: str | None = None,
        since: float | None = None,
    ) -> int:
        """Count events with optional filters."""
        conditions = []
        params: list = []
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        row = self._conn.execute(
            f"SELECT COUNT(*) as n FROM archive_index {where}", params
        ).fetchone()
        return row["n"]

    async def daily_summary(self, date: str | None = None) -> dict:
        """Get event counts by type for a given day (YYYY-MM-DD) or today."""
        if date:
            parts = date.split("-")
            dt = datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=timezone.utc)
        else:
            dt = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        start = dt.timestamp()
        end = start + 86400

        rows = self._conn.execute(
            """SELECT event_type, COUNT(*) as n
               FROM archive_index
               WHERE timestamp >= ? AND timestamp < ?
               GROUP BY event_type""",
            (start, end),
        ).fetchall()
        return {
            "date": dt.strftime("%Y-%m-%d"),
            "events": {r["event_type"]: r["n"] for r in rows},
            "total": sum(r["n"] for r in rows),
        }

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def stats(self) -> dict:
        """Overall archive statistics."""
        total = self._conn.execute("SELECT COUNT(*) as n FROM archive_index").fetchone()["n"]
        oldest = self._conn.execute("SELECT MIN(timestamp) as ts FROM archive_index").fetchone()["ts"]
        newest = self._conn.execute("SELECT MAX(timestamp) as ts FROM archive_index").fetchone()["ts"]

        # Count JSONL files
        file_count = sum(1 for _ in self._archive_dir.rglob("*.jsonl"))
        gz_count = sum(1 for _ in self._archive_dir.rglob("*.jsonl.gz"))

        # Disk usage
        total_bytes = sum(f.stat().st_size for f in self._archive_dir.rglob("*") if f.is_file())

        return {
            "total_events": total,
            "oldest_event": oldest,
            "newest_event": newest,
            "active_files": file_count,
            "compressed_files": gz_count,
            "disk_usage_mb": round(total_bytes / (1024 * 1024), 2),
            "user_tracking_enabled": self._user_tracking_enabled,
        }

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def compress_old_files(self, days_old: int = 1) -> int:
        """Gzip JSONL files older than N days. Returns count compressed."""
        cutoff = time.time() - (days_old * 86400)
        compressed = 0
        for jsonl in self._archive_dir.rglob("*.jsonl"):
            if jsonl.stat().st_mtime < cutoff:
                gz_path = jsonl.with_suffix(".jsonl.gz")
                if gz_path.exists():
                    continue
                with open(jsonl, "rb") as f_in:
                    with gzip.open(gz_path, "wb") as f_out:
                        f_out.write(f_in.read())
                jsonl.unlink()
                compressed += 1
        return compressed

    async def export_day(self, date: str) -> list[dict]:
        """Export all events for a specific day as a list of dicts."""
        parts = date.split("-")
        path = self._archive_dir / parts[0] / parts[1] / f"{parts[2]}.jsonl"
        gz_path = path.with_suffix(".jsonl.gz")

        events = []
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        elif gz_path.exists():
            with gzip.open(gz_path, "rt", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        events.append(json.loads(line))
        return events
