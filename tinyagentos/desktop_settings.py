from __future__ import annotations
import json
from pathlib import Path
from tinyagentos.base_store import BaseStore

DEFAULT_SETTINGS = {
    "mode": "dark",
    "accentColor": "#667eea",
    "wallpaper": "default",
    "dockMagnification": False,
    "topBarOpacity": 0.95,
}

DEFAULT_DOCK = {
    "pinned": ["messages", "agents", "files", "store", "settings"],
}


class DesktopSettingsStore(BaseStore):
    SCHEMA = """
    CREATE TABLE IF NOT EXISTS desktop_settings (
        user_id TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (user_id, key)
    );
    """

    async def _get(self, user_id: str, key: str, default: dict) -> dict:
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT value FROM desktop_settings WHERE user_id = ? AND key = ?",
            (user_id, key),
        )
        row = await cursor.fetchone()
        if row:
            saved = json.loads(row[0])
            merged = {**default, **saved}
            return merged
        return dict(default)

    async def _set(self, user_id: str, key: str, value: dict) -> None:
        assert self._db is not None
        await self._db.execute(
            "INSERT INTO desktop_settings (user_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
            (user_id, key, json.dumps(value)),
        )
        await self._db.commit()

    async def get_settings(self, user_id: str) -> dict:
        settings = await self._get(user_id, "settings", DEFAULT_SETTINGS)
        dock = await self.get_dock(user_id)
        settings["dock"] = dock
        return settings

    async def update_settings(self, user_id: str, updates: dict) -> None:
        current = await self._get(user_id, "settings", DEFAULT_SETTINGS)
        current.update(updates)
        await self._set(user_id, "settings", current)

    async def get_dock(self, user_id: str) -> dict:
        return await self._get(user_id, "dock", DEFAULT_DOCK)

    async def update_dock(self, user_id: str, updates: dict) -> None:
        current = await self.get_dock(user_id)
        current.update(updates)
        await self._set(user_id, "dock", current)

    async def get_windows(self, user_id: str) -> list:
        data = await self._get(user_id, "windows", {"positions": []})
        return data.get("positions", [])

    async def save_windows(self, user_id: str, positions: list) -> None:
        await self._set(user_id, "windows", {"positions": positions})
