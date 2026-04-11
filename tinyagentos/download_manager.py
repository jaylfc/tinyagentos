from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


@dataclass
class DownloadTask:
    id: str
    url: str
    dest: Path
    total_bytes: int = 0
    downloaded_bytes: int = 0
    status: str = "pending"  # pending | downloading | complete | error
    error: str = ""
    started_at: float = 0
    completed_at: float = 0


class DownloadManager:
    def __init__(self):
        self._tasks: dict[str, DownloadTask] = {}
        self._running: dict[str, asyncio.Task] = {}

    def start_download(
        self,
        download_id: str,
        url: str,
        dest: Path,
        expected_sha256: str | None = None,
    ) -> DownloadTask:
        task = DownloadTask(id=download_id, url=url, dest=dest)
        self._tasks[download_id] = task
        self._running[download_id] = asyncio.create_task(
            self._download(task, expected_sha256)
        )
        return task

    def get_progress(self, download_id: str) -> DownloadTask | None:
        return self._tasks.get(download_id)

    def list_active(self) -> list[DownloadTask]:
        return [t for t in self._tasks.values() if t.status in ("pending", "downloading")]

    def list_all(self) -> list[DownloadTask]:
        return list(self._tasks.values())

    async def _download(self, task: DownloadTask, expected_sha256: str | None = None):
        task.status = "downloading"
        task.started_at = time.time()
        sha = hashlib.sha256()
        try:
            task.dest.parent.mkdir(parents=True, exist_ok=True)
            async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
                async with client.stream("GET", task.url) as resp:
                    resp.raise_for_status()
                    total = resp.headers.get("content-length")
                    task.total_bytes = int(total) if total else 0
                    with open(task.dest, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                            sha.update(chunk)
                            task.downloaded_bytes += len(chunk)
            if expected_sha256 and sha.hexdigest() != expected_sha256:
                task.dest.unlink(missing_ok=True)
                task.status = "error"
                task.error = "SHA256 mismatch"
            else:
                task.status = "complete"
                task.completed_at = time.time()
        except Exception as e:
            task.status = "error"
            task.error = str(e)
            logger.error(f"Download failed for {task.id}: {e}")
