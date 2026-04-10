from __future__ import annotations
import time
from tinyagentos.base_store import BaseStore


class InstalledAppsStore(BaseStore):
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS installed_apps (
        app_id TEXT PRIMARY KEY,
        installed_at REAL NOT NULL,
        version TEXT DEFAULT '',
        metadata TEXT DEFAULT '{}'
    );
    """

    async def install(self, app_id: str, version: str = "", metadata: dict | None = None) -> None:
        import json
        assert self._db is not None
        await self._db.execute(
            "INSERT OR REPLACE INTO installed_apps (app_id, installed_at, version, metadata) VALUES (?, ?, ?, ?)",
            (app_id, time.time(), version, json.dumps(metadata or {})),
        )
        await self._db.commit()

    async def uninstall(self, app_id: str) -> bool:
        assert self._db is not None
        cursor = await self._db.execute(
            "DELETE FROM installed_apps WHERE app_id = ?",
            (app_id,),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def is_installed(self, app_id: str) -> bool:
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT 1 FROM installed_apps WHERE app_id = ?",
            (app_id,),
        )
        return await cursor.fetchone() is not None

    async def list_installed(self) -> list[dict]:
        import json
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT app_id, installed_at, version, metadata FROM installed_apps ORDER BY installed_at DESC"
        )
        rows = await cursor.fetchall()
        return [
            {"app_id": r[0], "installed_at": r[1], "version": r[2], "metadata": json.loads(r[3] or "{}")}
            for r in rows
        ]
