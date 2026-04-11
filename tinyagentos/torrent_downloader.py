"""libtorrent-backed download path for model weights.

Phase 1 of the model torrent mesh (see docs/design/model-torrent-mesh.md).
A hybrid client download that prefers the swarm and falls back to HTTP
when there are no peers or the variant's licence doesn't allow
redistribution.

Model sharing is a core part of TinyAgentOS — every install is a
potential seeder, and libtorrent is a required runtime dependency.
The worker install scripts pull it in via the OS package manager
(``libtorrent-rasterbar`` on Debian/Ubuntu/Fedora/Arch, brew on
macOS) plus a pip wheel for the Python binding. The try/except
around the import is kept only for the narrow case of an install on
a platform without a pip wheel — on those hosts ``TorrentNotAvailable``
fires and the DownloadManager falls back to HTTP so the user still
gets their models.

Public contract:

- ``TORRENT_AVAILABLE`` — True iff libtorrent imported successfully
- ``TorrentNotAvailable`` — raised on hosts without libtorrent (rare)
- ``TorrentDownloader`` — wraps a single-session libtorrent handle
  with an async download() method that mirrors DownloadManager's
  progress semantics
- ``should_use_torrent(variant, seed_enabled)`` — policy gate:
  checks licence allowance and library availability

Phase 2 adds the mirror seedbox, tracker, and catalog-publish CLI.
Phase 3 adds seeding UX, per-model opt-out, and Tailscale-only mode.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


try:
    import libtorrent as lt  # type: ignore
    TORRENT_AVAILABLE = True
except ImportError:
    lt = None  # type: ignore
    TORRENT_AVAILABLE = False


class TorrentError(Exception):
    """Base class for all torrent download errors."""


class TorrentNotAvailable(TorrentError):
    """Raised when libtorrent is not installed on this host.

    Callers should catch this and fall back to HTTP download. The
    TinyAgentOS install story treats libtorrent as an optional
    dependency — workers without it still download models, just over
    HTTP instead of the swarm.
    """


class TorrentTimeout(TorrentError):
    """Raised when the torrent swarm doesn't produce any peers within
    the grace period. Callers should fall back to HTTP."""


@dataclass
class TorrentTask:
    """Progress + state of one torrent download."""
    id: str
    dest: Path
    magnet_or_torrent: str  # magnet URI or http URL to .torrent file
    total_bytes: int = 0
    downloaded_bytes: int = 0
    num_peers: int = 0
    upload_rate_bps: float = 0.0
    download_rate_bps: float = 0.0
    status: str = "pending"  # pending | downloading | seeding | complete | error
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0


def should_use_torrent(variant: dict, seed_enabled: bool) -> bool:
    """Decide whether a variant should try the torrent path first.

    Policy:

    1. libtorrent must be installed
    2. The manifest must declare either ``magnet`` or ``torrent_url``
    3. The manifest must set ``license_allows_redistribution: true``
       (default: False — we do not redistribute by default, only when
       the catalog publisher has explicitly marked the variant as
       allowed per its licence)
    4. Seed mode doesn't gate *download*; seeding is a post-download
       choice. This function answers 'should we TRY the torrent path'
       not 'should we keep seeding after completion'.

    The ``seed_enabled`` argument is accepted so the function can be
    extended later (e.g. 'only use torrent when seeding is enabled
    OR when the HTTP source is rate-limited') without changing the
    call sites.
    """
    if not TORRENT_AVAILABLE:
        return False
    if not (variant.get("magnet") or variant.get("torrent_url")):
        return False
    if not variant.get("license_allows_redistribution", False):
        return False
    return True


class TorrentDownloader:
    """Single libtorrent session used by the DownloadManager.

    One session handles the whole process — add_torrent for each new
    download, poll status at 1Hz, emit progress via the task object.
    Completed downloads remain in the session (seeding) until removed
    via ``release()``.
    """

    def __init__(
        self,
        *,
        listen_port_range: tuple[int, int] = (6881, 6889),
        download_rate_limit: int = 0,  # 0 = unlimited
        upload_rate_limit: int = 0,
        peer_timeout_seconds: float = 30.0,
    ):
        if not TORRENT_AVAILABLE:
            raise TorrentNotAvailable(
                "libtorrent is not installed — install python-libtorrent "
                "to enable the torrent download path"
            )
        self._session = lt.session({
            "listen_interfaces": f"0.0.0.0:{listen_port_range[0]}",
            "enable_dht": True,
            "enable_lsd": True,
            "enable_upnp": True,
            "enable_natpmp": True,
            "download_rate_limit": download_rate_limit,
            "upload_rate_limit": upload_rate_limit,
        })
        self._peer_timeout = peer_timeout_seconds
        self._handles: dict[str, "lt.torrent_handle"] = {}  # type: ignore
        self._tasks: dict[str, TorrentTask] = {}

    def list_tasks(self) -> list[TorrentTask]:
        return list(self._tasks.values())

    def get_task(self, task_id: str) -> Optional[TorrentTask]:
        return self._tasks.get(task_id)

    async def download(
        self,
        task_id: str,
        magnet_or_torrent: str,
        dest: Path,
        expected_sha256: Optional[str] = None,
        progress_cb: Optional[Callable[[TorrentTask], None]] = None,
    ) -> TorrentTask:
        """Start a torrent download and poll to completion.

        Raises :class:`TorrentTimeout` if no peers are found within
        ``peer_timeout_seconds`` — the caller should catch and fall back
        to the HTTP path.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        task = TorrentTask(
            id=task_id,
            dest=dest,
            magnet_or_torrent=magnet_or_torrent,
            started_at=time.time(),
            status="downloading",
        )
        self._tasks[task_id] = task

        params = lt.parse_magnet_uri(magnet_or_torrent) if magnet_or_torrent.startswith("magnet:") else None
        if params is None:
            raise TorrentError("torrent_url fetching not yet implemented — use magnet URIs in Phase 1")
        params.save_path = str(dest.parent)
        handle = self._session.add_torrent(params)
        self._handles[task_id] = handle

        # Wait for peers or timeout
        peer_wait_start = time.time()
        while True:
            await asyncio.sleep(1)
            status = handle.status()
            task.num_peers = status.num_peers
            task.total_bytes = status.total_wanted
            task.downloaded_bytes = status.total_wanted_done
            task.download_rate_bps = status.download_rate
            task.upload_rate_bps = status.upload_rate

            if status.state == lt.torrent_status.seeding or status.progress >= 1.0:
                task.status = "complete"
                task.completed_at = time.time()
                break

            if task.num_peers == 0 and (time.time() - peer_wait_start) > self._peer_timeout:
                task.status = "error"
                task.error = f"no peers within {self._peer_timeout}s"
                raise TorrentTimeout(task.error)

            if progress_cb is not None:
                try:
                    progress_cb(task)
                except Exception:
                    logger.exception("torrent progress_cb raised")

        # Optional SHA256 verification against the expected hash
        if expected_sha256 and dest.exists():
            actual = hashlib.sha256(dest.read_bytes()).hexdigest()
            if actual.lower() != expected_sha256.lower():
                task.status = "error"
                task.error = "sha256 mismatch"
                raise TorrentError("sha256 mismatch after torrent download")

        return task

    def release(self, task_id: str, delete_files: bool = False) -> None:
        """Remove a torrent from the session.

        With ``delete_files=False`` (the default) the handle is dropped
        but the file stays on disk — this is how seeding stops while
        keeping the model available locally. With ``delete_files=True``
        the file is also removed, matching the behaviour of an HTTP
        ``rm``."""
        handle = self._handles.pop(task_id, None)
        if handle is not None:
            flags = lt.session.delete_files if delete_files else 0
            try:
                self._session.remove_torrent(handle, flags)
            except Exception:
                logger.exception("failed to remove torrent %s", task_id)
        self._tasks.pop(task_id, None)

    def shutdown(self) -> None:
        """Release the session entirely. Seeding stops."""
        for task_id in list(self._handles.keys()):
            self.release(task_id, delete_files=False)
