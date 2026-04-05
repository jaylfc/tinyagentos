from __future__ import annotations

import base64
import hashlib
import time
from pathlib import Path

import aiosqlite

SECRETS_SCHEMA = """
CREATE TABLE IF NOT EXISTS secrets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT 'general',
    value TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS secret_access (
    secret_id INTEGER NOT NULL,
    agent_name TEXT NOT NULL,
    PRIMARY KEY (secret_id, agent_name),
    FOREIGN KEY (secret_id) REFERENCES secrets(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS secret_categories (
    name TEXT PRIMARY KEY,
    description TEXT DEFAULT ''
);
"""

DEFAULT_CATEGORIES = ["api-keys", "tokens", "credentials", "webhooks", "general"]


# Simple XOR-based obfuscation with machine-specific key
# Not military-grade crypto, but prevents casual reading of the DB file
def _get_key() -> bytes:
    machine_id_path = Path("/etc/machine-id")
    machine_id = (
        machine_id_path.read_text().strip()
        if machine_id_path.exists()
        else "tinyagentos-default"
    )
    return hashlib.sha256(machine_id.encode()).digest()


def _encrypt(value: str) -> str:
    key = _get_key()
    data = value.encode()
    encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.b64encode(encrypted).decode()


def _decrypt(encrypted: str) -> str:
    key = _get_key()
    data = base64.b64decode(encrypted)
    decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return decrypted.decode()


class SecretsStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.executescript(SECRETS_SCHEMA)
        await self._db.commit()
        # Seed default categories
        for cat in DEFAULT_CATEGORIES:
            await self._db.execute(
                "INSERT OR IGNORE INTO secret_categories (name) VALUES (?)", (cat,)
            )
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def add(
        self,
        name: str,
        value: str,
        category: str = "general",
        description: str = "",
        agents: list[str] | None = None,
    ) -> int:
        now = int(time.time())
        encrypted = _encrypt(value)
        cursor = await self._db.execute(
            "INSERT INTO secrets (name, category, value, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (name, category, encrypted, description, now, now),
        )
        secret_id = cursor.lastrowid
        if agents:
            for agent in agents:
                await self._db.execute(
                    "INSERT INTO secret_access (secret_id, agent_name) VALUES (?, ?)",
                    (secret_id, agent),
                )
        await self._db.commit()
        return secret_id

    async def get(self, name: str) -> dict | None:
        async with self._db.execute(
            "SELECT id, name, category, value, description, created_at, updated_at FROM secrets WHERE name = ?",
            (name,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        agents = await self._get_agents(row[0])
        return {
            "id": row[0],
            "name": row[1],
            "category": row[2],
            "value": _decrypt(row[3]),
            "description": row[4],
            "created_at": row[5],
            "updated_at": row[6],
            "agents": agents,
        }

    async def list(self, category: str | None = None) -> list[dict]:
        sql = "SELECT id, name, category, description, created_at, updated_at FROM secrets"
        params: list = []
        if category:
            sql += " WHERE category = ?"
            params.append(category)
        sql += " ORDER BY category, name"
        async with self._db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
        results = []
        for r in rows:
            agents = await self._get_agents(r[0])
            results.append(
                {
                    "id": r[0],
                    "name": r[1],
                    "category": r[2],
                    "description": r[3],
                    "created_at": r[4],
                    "updated_at": r[5],
                    "agents": agents,
                }
            )
        return results

    async def update(
        self,
        name: str,
        value: str | None = None,
        category: str | None = None,
        description: str | None = None,
        agents: list[str] | None = None,
    ) -> bool:
        secret = await self.get(name)
        if not secret:
            return False
        now = int(time.time())
        if value is not None:
            await self._db.execute(
                "UPDATE secrets SET value = ?, updated_at = ? WHERE name = ?",
                (_encrypt(value), now, name),
            )
        if category is not None:
            await self._db.execute(
                "UPDATE secrets SET category = ?, updated_at = ? WHERE name = ?",
                (category, now, name),
            )
        if description is not None:
            await self._db.execute(
                "UPDATE secrets SET description = ?, updated_at = ? WHERE name = ?",
                (description, now, name),
            )
        if agents is not None:
            await self._db.execute(
                "DELETE FROM secret_access WHERE secret_id = ?", (secret["id"],)
            )
            for agent in agents:
                await self._db.execute(
                    "INSERT INTO secret_access (secret_id, agent_name) VALUES (?, ?)",
                    (secret["id"], agent),
                )
        await self._db.commit()
        return True

    async def delete(self, name: str) -> bool:
        cursor = await self._db.execute("DELETE FROM secrets WHERE name = ?", (name,))
        await self._db.commit()
        return cursor.rowcount > 0

    async def get_agent_secrets(self, agent_name: str) -> list[dict]:
        """Get all secrets accessible to a specific agent."""
        async with self._db.execute(
            """
            SELECT s.id, s.name, s.category, s.value, s.description
            FROM secrets s
            JOIN secret_access sa ON sa.secret_id = s.id
            WHERE sa.agent_name = ?
            ORDER BY s.category, s.name
            """,
            (agent_name,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "category": r[2],
                "value": _decrypt(r[3]),
                "description": r[4],
            }
            for r in rows
        ]

    async def get_categories(self) -> list[dict]:
        async with self._db.execute(
            "SELECT name, description FROM secret_categories ORDER BY name"
        ) as cursor:
            return [{"name": r[0], "description": r[1]} for r in await cursor.fetchall()]

    async def _get_agents(self, secret_id: int) -> list[str]:
        async with self._db.execute(
            "SELECT agent_name FROM secret_access WHERE secret_id = ?", (secret_id,)
        ) as cursor:
            return [r[0] for r in await cursor.fetchall()]
