from __future__ import annotations

import time
from pathlib import Path

from tinyagentos.base_store import BaseStore

NOTIF_SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    level TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    read INTEGER NOT NULL DEFAULT 0,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_notif_ts ON notifications(timestamp DESC);
"""


class NotificationStore(BaseStore):
    SCHEMA = NOTIF_SCHEMA

    async def add(self, title: str, message: str, level: str = "info", source: str = "system") -> None:
        ts = int(time.time())
        await self._db.execute(
            "INSERT INTO notifications (timestamp, level, title, message, source) VALUES (?, ?, ?, ?, ?)",
            (ts, level, title, message, source),
        )
        await self._db.commit()

    async def list(self, limit: int = 20, unread_only: bool = False) -> list[dict]:
        sql = "SELECT id, timestamp, level, title, message, read, source FROM notifications"
        if unread_only:
            sql += " WHERE read = 0"
        sql += " ORDER BY timestamp DESC LIMIT ?"
        async with self._db.execute(sql, (limit,)) as cursor:
            rows = await cursor.fetchall()
        return [
            {"id": r[0], "timestamp": r[1], "level": r[2], "title": r[3],
             "message": r[4], "read": bool(r[5]), "source": r[6]}
            for r in rows
        ]

    async def unread_count(self) -> int:
        async with self._db.execute("SELECT COUNT(*) FROM notifications WHERE read = 0") as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0

    async def mark_read(self, notif_id: int) -> None:
        await self._db.execute("UPDATE notifications SET read = 1 WHERE id = ?", (notif_id,))
        await self._db.commit()

    async def mark_all_read(self) -> None:
        await self._db.execute("UPDATE notifications SET read = 1")
        await self._db.commit()

    async def cleanup(self, max_age_days: int = 30) -> int:
        cutoff = int(time.time()) - (max_age_days * 86400)
        cursor = await self._db.execute("DELETE FROM notifications WHERE timestamp < ?", (cutoff,))
        await self._db.commit()
        return cursor.rowcount
