"""Hourly auto-update checker.

Polls the configured git remote once an hour, notifies the user when new
commits land, and optionally applies them automatically. De-dupes
notifications via the "last notified commit" marker so the user gets one
notification per new release, not one per poll cycle.

Uses ``asyncio.create_subprocess_exec`` (list-of-args, never shell) so
untrusted paths cannot cause command injection.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# How often to check for updates (seconds). One hour by default.
CHECK_INTERVAL = 60 * 60

# Namespace used in /api/preferences/auto-update for user settings.
PREF_NAMESPACE = "auto-update"

# Defaults the user gets on a fresh install — auto-apply off, check on.
DEFAULT_PREFS = {
    "check_enabled": True,
    "auto_apply": False,
    "last_notified_commit": None,
}


async def _run(args: list[str], cwd: Path) -> tuple[int, str]:
    """Run a subprocess safely (no shell) and return (returncode, output)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=str(cwd),
    )
    stdout, _ = await proc.communicate()
    return proc.returncode or 0, (stdout.decode() if stdout else "")


class AutoUpdateService:
    """Background service that periodically checks GitHub for updates.

    Depends on:
        - ``notif_store`` for firing user notifications
        - ``settings_store`` for reading user prefs (auto-apply
          toggle, dedupe marker)

    Start with ``start()`` during app lifespan, stop with ``stop()``.
    """

    def __init__(self, project_dir: Path, notif_store, settings_store):
        self._project_dir = project_dir
        self._notif = notif_store
        self._settings = settings_store
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="auto-update-checker")
        logger.info("AutoUpdateService started (interval=%ds)", CHECK_INTERVAL)

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _loop(self) -> None:
        # Small initial delay so we don't slam GitHub the instant the
        # server boots — space out with the rest of startup.
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=90)
            return
        except asyncio.TimeoutError:
            pass

        while True:
            try:
                await self._run_once()
            except Exception:
                logger.exception("auto-update check failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=CHECK_INTERVAL)
                return
            except asyncio.TimeoutError:
                pass  # tick again

    async def _run_once(self) -> None:
        prefs = await self._get_prefs()
        if not prefs.get("check_enabled", True):
            return

        # Fetch latest from origin/master
        new_commit = await self._probe_remote()
        if new_commit is None:
            return

        current = await self._current_commit()
        if new_commit == current:
            return  # already up to date

        # Skip re-notifying for a commit we've already flagged.
        if prefs.get("last_notified_commit") == new_commit:
            if prefs.get("auto_apply"):
                await self._auto_apply(new_commit)
            return

        if prefs.get("auto_apply"):
            await self._auto_apply(new_commit)
        else:
            await self._notify_available(current, new_commit)

        # Remember so we don't re-notify next hour.
        prefs["last_notified_commit"] = new_commit
        await self._save_prefs(prefs)

    async def _probe_remote(self) -> Optional[str]:
        """Return the current HEAD commit of origin/master, or None on failure."""
        rc, _ = await _run(
            ["git", "fetch", "--quiet", "origin", "master"], self._project_dir
        )
        if rc != 0:
            return None
        rc2, out = await _run(["git", "rev-parse", "origin/master"], self._project_dir)
        if rc2 != 0:
            return None
        return out.strip()

    async def _current_commit(self) -> str:
        rc, out = await _run(["git", "rev-parse", "HEAD"], self._project_dir)
        return out.strip() if rc == 0 else ""

    async def _notify_available(self, current: str, new_commit: str) -> None:
        short_old = (current or "")[:7]
        short_new = new_commit[:7]
        await self._notif.add_notification(
            source="system",
            event_type="system.update",
            title="taOS update available",
            body=f"A new version is ready ({short_old}->{short_new}). Open Settings to install.",
            level="info",
        )
        logger.info("Notified user of update: %s -> %s", short_old, short_new)

    async def _auto_apply(self, new_commit: str) -> None:
        """Pull + install + notify restart needed."""
        logger.info("Auto-applying update to %s", new_commit[:7])

        rc, out = await _run(
            ["git", "pull", "--ff-only", "origin", "master"], self._project_dir
        )
        if rc != 0:
            logger.error("auto-update pull failed: %s", out[:500])
            return

        pip_cmd = str(Path(sys.executable).parent / "pip")
        await _run([pip_cmd, "install", "-e", ".", "-q"], self._project_dir)

        await self._notif.add_notification(
            source="system",
            event_type="system.update",
            title="taOS updated automatically",
            body=f"Pulled {new_commit[:7]}. Restart the server to finish applying.",
            level="info",
        )

    async def _get_prefs(self) -> dict:
        try:
            saved = await self._settings.get_preference("user", PREF_NAMESPACE)
            return {**DEFAULT_PREFS, **(saved or {})}
        except Exception:
            return dict(DEFAULT_PREFS)

    async def _save_prefs(self, prefs: dict) -> None:
        try:
            await self._settings.save_preference("user", PREF_NAMESPACE, prefs)
        except Exception:
            logger.exception("failed to save auto-update prefs")
