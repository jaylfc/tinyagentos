from __future__ import annotations

import json
import time

from tinyagentos.base_store import BaseStore

MESSAGES_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    message TEXT NOT NULL,
    tool_calls TEXT DEFAULT '[]',
    tool_results TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}',
    timestamp REAL NOT NULL,
    read INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_msg_from ON agent_messages(from_agent, timestamp);
CREATE INDEX IF NOT EXISTS idx_msg_to ON agent_messages(to_agent, timestamp);
"""


class AgentMessageStore(BaseStore):
    SCHEMA = MESSAGES_SCHEMA

    async def send(self, from_agent: str, to_agent: str, message: str,
                   tool_calls: list | None = None, tool_results: list | None = None,
                   metadata: dict | None = None) -> int:
        now = time.time()
        cursor = await self._db.execute(
            "INSERT INTO agent_messages (from_agent, to_agent, message, tool_calls, tool_results, metadata, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (from_agent, to_agent, message, json.dumps(tool_calls or []),
             json.dumps(tool_results or []), json.dumps(metadata or {}), now))
        await self._db.commit()
        return cursor.lastrowid

    async def get_messages(self, agent_name: str, limit: int = 50) -> list[dict]:
        """Get all messages involving an agent (sent or received)."""
        async with self._db.execute(
            """SELECT id, from_agent, to_agent, message, tool_calls, tool_results, metadata, timestamp, read
               FROM agent_messages WHERE from_agent = ? OR to_agent = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (agent_name, agent_name, limit)
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {"id": r[0], "from": r[1], "to": r[2], "message": r[3],
             "tool_calls": json.loads(r[4]), "tool_results": json.loads(r[5]),
             "metadata": json.loads(r[6]), "timestamp": r[7], "read": bool(r[8])}
            for r in rows
        ]

    async def get_conversation(self, agent1: str, agent2: str, limit: int = 50) -> list[dict]:
        """Get messages between two specific agents."""
        async with self._db.execute(
            """SELECT id, from_agent, to_agent, message, tool_calls, tool_results, metadata, timestamp
               FROM agent_messages
               WHERE (from_agent = ? AND to_agent = ?) OR (from_agent = ? AND to_agent = ?)
               ORDER BY timestamp ASC LIMIT ?""",
            (agent1, agent2, agent2, agent1, limit)
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {"id": r[0], "from": r[1], "to": r[2], "message": r[3],
             "tool_calls": json.loads(r[4]), "tool_results": json.loads(r[5]),
             "metadata": json.loads(r[6]), "timestamp": r[7]}
            for r in rows
        ]

    async def mark_read(self, agent_name: str):
        await self._db.execute("UPDATE agent_messages SET read = 1 WHERE to_agent = ?", (agent_name,))
        await self._db.commit()

    async def unread_count(self, agent_name: str) -> int:
        async with self._db.execute(
            "SELECT COUNT(*) FROM agent_messages WHERE to_agent = ? AND read = 0", (agent_name,)
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else 0
