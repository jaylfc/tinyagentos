"""Worker Heartbeat Protocol (taOSmd).

Workers periodically report their capabilities to the controller so the
resource manager can make informed scheduling decisions. Each heartbeat
includes: hardware specs, loaded models, GPU utilisation, RAM availability,
and job capacity.

Controller side: receives heartbeats, maintains a registry of online workers.
Worker side: sends heartbeats at a configurable interval.

Workers that miss 3 consecutive heartbeats are considered offline.
The resource manager's evaluate_migration() detects this and triggers
fallback to local models.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS workers (
    name TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    last_heartbeat REAL NOT NULL,
    cpu_cores INTEGER NOT NULL DEFAULT 0,
    npu_cores INTEGER NOT NULL DEFAULT 0,
    gpu_name TEXT,
    gpu_vram_mb INTEGER NOT NULL DEFAULT 0,
    gpu_utilisation INTEGER NOT NULL DEFAULT 0,
    ram_total_mb INTEGER NOT NULL DEFAULT 0,
    ram_available_mb INTEGER NOT NULL DEFAULT 0,
    models_json TEXT NOT NULL DEFAULT '[]',
    is_yielded INTEGER NOT NULL DEFAULT 0,
    worker_type TEXT NOT NULL DEFAULT 'general',
    registered_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workers_heartbeat ON workers(last_heartbeat);
"""

# Worker is offline if no heartbeat for this many seconds
OFFLINE_THRESHOLD = 90  # 3 missed heartbeats at 30s interval


class WorkerRegistry:
    """Controller-side registry of cluster workers."""

    def __init__(self, db_path: str | Path = "data/workers.db"):
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

    async def receive_heartbeat(self, heartbeat: dict) -> dict:
        """Process a heartbeat from a worker.

        Args:
            heartbeat: {
                name: str,
                url: str,
                cpu_cores: int,
                npu_cores: int,
                gpu_name: str | None,
                gpu_vram_mb: int,
                gpu_utilisation: int (0-100),
                ram_total_mb: int,
                ram_available_mb: int,
                models: list[str],
                is_yielded: bool,
                worker_type: str ("general" | "gaming" | "headless" | "mobile"),
            }
        """
        import json
        now = time.time()
        name = heartbeat["name"]

        self._conn.execute(
            """INSERT INTO workers (name, url, last_heartbeat, cpu_cores, npu_cores,
               gpu_name, gpu_vram_mb, gpu_utilisation, ram_total_mb, ram_available_mb,
               models_json, is_yielded, worker_type, registered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 url = excluded.url,
                 last_heartbeat = excluded.last_heartbeat,
                 cpu_cores = excluded.cpu_cores,
                 npu_cores = excluded.npu_cores,
                 gpu_name = excluded.gpu_name,
                 gpu_vram_mb = excluded.gpu_vram_mb,
                 gpu_utilisation = excluded.gpu_utilisation,
                 ram_total_mb = excluded.ram_total_mb,
                 ram_available_mb = excluded.ram_available_mb,
                 models_json = excluded.models_json,
                 is_yielded = excluded.is_yielded,
                 worker_type = excluded.worker_type""",
            (name, heartbeat.get("url", ""), now,
             heartbeat.get("cpu_cores", 0), heartbeat.get("npu_cores", 0),
             heartbeat.get("gpu_name"), heartbeat.get("gpu_vram_mb", 0),
             heartbeat.get("gpu_utilisation", 0),
             heartbeat.get("ram_total_mb", 0), heartbeat.get("ram_available_mb", 0),
             json.dumps(heartbeat.get("models", [])),
             1 if heartbeat.get("is_yielded") else 0,
             heartbeat.get("worker_type", "general"), now),
        )
        self._conn.commit()
        return {"status": "ok", "worker": name}

    async def online_workers(self) -> list[dict]:
        """Get all workers with a recent heartbeat."""
        import json
        cutoff = time.time() - OFFLINE_THRESHOLD
        rows = self._conn.execute(
            "SELECT * FROM workers WHERE last_heartbeat > ? ORDER BY name",
            (cutoff,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["models"] = json.loads(d.pop("models_json", "[]"))
            d["gpu"] = bool(d.get("gpu_name"))
            d["online"] = True
            result.append(d)
        return result

    async def all_workers(self) -> list[dict]:
        """Get all known workers (online and offline)."""
        import json
        cutoff = time.time() - OFFLINE_THRESHOLD
        rows = self._conn.execute(
            "SELECT * FROM workers ORDER BY last_heartbeat DESC"
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["models"] = json.loads(d.pop("models_json", "[]"))
            d["gpu"] = bool(d.get("gpu_name"))
            d["online"] = d["last_heartbeat"] > cutoff
            result.append(d)
        return result

    async def get_worker(self, name: str) -> dict | None:
        """Get a specific worker's status."""
        import json
        row = self._conn.execute(
            "SELECT * FROM workers WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["models"] = json.loads(d.pop("models_json", "[]"))
        d["gpu"] = bool(d.get("gpu_name"))
        d["online"] = d["last_heartbeat"] > (time.time() - OFFLINE_THRESHOLD)
        return d

    async def remove_worker(self, name: str) -> bool:
        """Remove a worker from the registry."""
        cursor = self._conn.execute("DELETE FROM workers WHERE name = ?", (name,))
        self._conn.commit()
        return cursor.rowcount > 0

    async def for_resource_manager(self) -> list[dict]:
        """Get online workers formatted for the resource manager's snapshot.

        Returns the format that ResourceSnapshot.cluster_workers expects.
        """
        workers = await self.online_workers()
        return [
            {
                "name": w["name"],
                "gpu": w["gpu"],
                "models": w["models"],
                "gpu_utilisation": w.get("gpu_utilisation", 0),
                "cpu_cores": w.get("cpu_cores", 0),
                "ram_available_mb": w.get("ram_available_mb", 0),
                "is_yielded": bool(w.get("is_yielded")),
                "worker_type": w.get("worker_type", "general"),
            }
            for w in workers
            if not w.get("is_yielded")  # Exclude yielded workers from scheduling
        ]

    async def stats(self) -> dict:
        cutoff = time.time() - OFFLINE_THRESHOLD
        total = self._conn.execute("SELECT COUNT(*) as n FROM workers").fetchone()["n"]
        online = self._conn.execute(
            "SELECT COUNT(*) as n FROM workers WHERE last_heartbeat > ?", (cutoff,)
        ).fetchone()["n"]
        gpu_workers = self._conn.execute(
            "SELECT COUNT(*) as n FROM workers WHERE gpu_name IS NOT NULL AND last_heartbeat > ?",
            (cutoff,),
        ).fetchone()["n"]
        return {"total_workers": total, "online": online, "gpu_workers": gpu_workers}
