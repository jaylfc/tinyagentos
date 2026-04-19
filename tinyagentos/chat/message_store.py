from __future__ import annotations

import json
import time
import uuid

from tinyagentos.base_store import BaseStore

MESSAGES_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    thread_id TEXT,
    author_id TEXT NOT NULL,
    author_type TEXT NOT NULL DEFAULT 'user',
    content TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT 'text',
    content_blocks TEXT NOT NULL DEFAULT '[]',
    embeds TEXT NOT NULL DEFAULT '[]',
    components TEXT NOT NULL DEFAULT '[]',
    attachments TEXT NOT NULL DEFAULT '[]',
    reactions TEXT NOT NULL DEFAULT '{}',
    state TEXT NOT NULL DEFAULT 'complete',
    edited_at REAL,
    pinned INTEGER NOT NULL DEFAULT 0,
    ephemeral INTEGER NOT NULL DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_channel ON chat_messages(channel_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_messages_thread ON chat_messages(thread_id);

CREATE TABLE IF NOT EXISTS chat_pins (
    channel_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    pinned_by TEXT NOT NULL,
    pinned_at REAL NOT NULL,
    PRIMARY KEY (channel_id, message_id)
);

CREATE TABLE IF NOT EXISTS chat_attachments (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    path TEXT NOT NULL,
    thumbnail_path TEXT,
    uploaded_by TEXT NOT NULL,
    uploaded_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_attachments_message ON chat_attachments(message_id);
"""

_JSON_FIELDS = ("content_blocks", "embeds", "components", "attachments", "reactions", "metadata")


def _parse(row: tuple, description) -> dict:
    keys = [d[0] for d in description]
    msg = dict(zip(keys, row))
    for field in _JSON_FIELDS:
        if field in msg and msg[field] is not None:
            msg[field] = json.loads(msg[field])
    if msg.get("metadata") is None:
        msg["metadata"] = {}
    return msg


class ChatMessageStore(BaseStore):
    SCHEMA = MESSAGES_SCHEMA

    async def send_message(
        self,
        channel_id: str,
        author_id: str,
        author_type: str,
        content: str,
        content_type: str = "text",
        thread_id: str | None = None,
        embeds: list | None = None,
        components: list | None = None,
        attachments: list | None = None,
        content_blocks: list | None = None,
        metadata: dict | None = None,
        state: str = "complete",
    ) -> dict:
        msg_id = uuid.uuid4().hex[:12]
        now = time.time()
        await self._db.execute(
            """INSERT INTO chat_messages
               (id, channel_id, thread_id, author_id, author_type, content,
                content_type, content_blocks, embeds, components, attachments,
                reactions, state, pinned, ephemeral, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)""",
            (
                msg_id, channel_id, thread_id, author_id, author_type, content,
                content_type,
                json.dumps(content_blocks or []),
                json.dumps(embeds or []),
                json.dumps(components or []),
                json.dumps(attachments or []),
                json.dumps({}),
                state,
                json.dumps(metadata or {}),
                now,
            ),
        )
        await self._db.commit()
        return await self.get_message(msg_id)

    async def get_message(self, message_id: str) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM chat_messages WHERE id = ?", (message_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return _parse(row, cursor.description)

    async def get_messages(
        self,
        channel_id: str,
        limit: int = 50,
        before: float | None = None,
        after: float | None = None,
    ) -> list[dict]:
        params: list = [channel_id]
        where = "channel_id = ?"
        if before is not None:
            where += " AND created_at < ?"
            params.append(before)
        if after is not None:
            where += " AND created_at > ?"
            params.append(after)
        params.append(limit)
        sql = f"""
            SELECT * FROM (
                SELECT * FROM chat_messages WHERE {where}
                ORDER BY created_at DESC LIMIT ?
            ) ORDER BY created_at ASC
        """
        async with self._db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            desc = cursor.description
        return [_parse(r, desc) for r in rows]

    async def edit_message(self, message_id: str, content: str) -> None:
        now = time.time()
        await self._db.execute(
            "UPDATE chat_messages SET content = ?, edited_at = ? WHERE id = ?",
            (content, now, message_id),
        )
        await self._db.commit()

    async def delete_message(self, message_id: str) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM chat_messages WHERE id = ?", (message_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def add_reaction(self, message_id: str, emoji: str, user_id: str) -> None:
        async with self._db.execute(
            "SELECT reactions FROM chat_messages WHERE id = ?", (message_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return
        reactions = json.loads(row[0])
        if emoji not in reactions:
            reactions[emoji] = []
        if user_id not in reactions[emoji]:
            reactions[emoji].append(user_id)
        await self._db.execute(
            "UPDATE chat_messages SET reactions = ? WHERE id = ?",
            (json.dumps(reactions), message_id),
        )
        await self._db.commit()

    async def remove_reaction(self, message_id: str, emoji: str, user_id: str) -> None:
        async with self._db.execute(
            "SELECT reactions FROM chat_messages WHERE id = ?", (message_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return
        reactions = json.loads(row[0])
        if emoji in reactions:
            reactions[emoji] = [u for u in reactions[emoji] if u != user_id]
            if not reactions[emoji]:
                del reactions[emoji]
        await self._db.execute(
            "UPDATE chat_messages SET reactions = ? WHERE id = ?",
            (json.dumps(reactions), message_id),
        )
        await self._db.commit()

    async def ensure_message(self, msg: dict) -> None:
        """Insert a message row only if its id is not already present (idempotent).

        ``msg`` must be a dict with at minimum ``id``, ``channel_id``,
        ``author_id``, ``author_type``, and ``created_at``.  All other fields
        fall back to their column defaults.
        """
        await self._db.execute(
            """INSERT OR IGNORE INTO chat_messages
               (id, channel_id, thread_id, author_id, author_type, content,
                content_type, content_blocks, embeds, components, attachments,
                reactions, state, edited_at, pinned, ephemeral, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg.get("id") or "",
                msg.get("channel_id") or "",
                msg.get("thread_id"),
                msg.get("author_id") or "",
                msg.get("author_type") or "user",
                msg.get("content") or "",
                msg.get("content_type") or "text",
                json.dumps(msg["content_blocks"]) if isinstance(msg.get("content_blocks"), list) else msg.get("content_blocks") or "[]",
                json.dumps(msg["embeds"]) if isinstance(msg.get("embeds"), list) else msg.get("embeds") or "[]",
                json.dumps(msg["components"]) if isinstance(msg.get("components"), list) else msg.get("components") or "[]",
                json.dumps(msg["attachments"]) if isinstance(msg.get("attachments"), list) else msg.get("attachments") or "[]",
                json.dumps(msg["reactions"]) if isinstance(msg.get("reactions"), dict) else msg.get("reactions") or "{}",
                msg.get("state") or "complete",
                msg.get("edited_at"),
                1 if msg.get("pinned") else 0,
                1 if msg.get("ephemeral") else 0,
                json.dumps(msg["metadata"]) if isinstance(msg.get("metadata"), dict) else msg.get("metadata") or "{}",
                msg.get("created_at") or time.time(),
            ),
        )
        await self._db.commit()

    async def get_thread_messages(
        self, channel_id: str, parent_id: str, limit: int = 20,
    ) -> list[dict]:
        """Return messages in a thread (not the parent), oldest first."""
        async with self._db.execute(
            "SELECT * FROM chat_messages "
            "WHERE channel_id = ? AND thread_id = ? "
            "ORDER BY created_at ASC LIMIT ?",
            (channel_id, parent_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            description = cursor.description
        return [_parse(row, description) for row in rows]

    async def get_all_messages_for_channel(self, channel_id: str) -> list[dict]:
        """Return every message in a channel ordered by created_at ASC.

        Used for chat-export on agent archive.  Loads all rows in one query;
        for very large histories this is acceptable since export runs once at
        archive time, not on hot paths.
        """
        sql = "SELECT * FROM chat_messages WHERE channel_id = ? ORDER BY created_at ASC"
        async with self._db.execute(sql, (channel_id,)) as cursor:
            rows = await cursor.fetchall()
            desc = cursor.description
        return [_parse(r, desc) for r in rows]

    async def delete_channel_messages(self, channel_id: str) -> int:
        """Delete all messages for a channel. Returns the number of rows deleted."""
        cursor = await self._db.execute(
            "DELETE FROM chat_messages WHERE channel_id = ?", (channel_id,)
        )
        await self._db.commit()
        return cursor.rowcount

    async def update_state(self, message_id: str, state: str) -> None:
        await self._db.execute(
            "UPDATE chat_messages SET state = ? WHERE id = ?", (state, message_id)
        )
        await self._db.commit()

    async def pin_message(self, channel_id: str, message_id: str, user_id: str) -> None:
        now = time.time()
        await self._db.execute(
            "INSERT OR REPLACE INTO chat_pins (channel_id, message_id, pinned_by, pinned_at) VALUES (?, ?, ?, ?)",
            (channel_id, message_id, user_id, now),
        )
        await self._db.execute(
            "UPDATE chat_messages SET pinned = 1 WHERE id = ?", (message_id,)
        )
        await self._db.commit()

    async def unpin_message(self, channel_id: str, message_id: str) -> None:
        await self._db.execute(
            "DELETE FROM chat_pins WHERE channel_id = ? AND message_id = ?",
            (channel_id, message_id),
        )
        await self._db.execute(
            "UPDATE chat_messages SET pinned = 0 WHERE id = ?", (message_id,)
        )
        await self._db.commit()

    async def search(
        self,
        query: str,
        channel_id: str | None = None,
        author_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        pattern = f"%{query}%"
        conditions = ["content LIKE ?"]
        params: list = [pattern]
        if channel_id is not None:
            conditions.append("channel_id = ?")
            params.append(channel_id)
        if author_id is not None:
            conditions.append("author_id = ?")
            params.append(author_id)
        params.append(limit)
        sql = f"SELECT * FROM chat_messages WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT ?"
        async with self._db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            desc = cursor.description
        return [_parse(r, desc) for r in rows]
