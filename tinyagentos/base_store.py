from __future__ import annotations
from pathlib import Path
import aiosqlite

class BaseStore:
    """Base class for all SQLite-backed stores."""
    SCHEMA: str = ""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        if self.SCHEMA:
            await self._db.executescript(self.SCHEMA)
            await self._db.commit()
        await self._post_init()

    async def _post_init(self) -> None:
        """Override in subclasses for seeding data after schema creation."""
        pass

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
