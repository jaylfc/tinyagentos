"""Framework update orchestrator. Owned one module; kicked off from the
route handler via asyncio.create_task per Phase 1's fire-and-track model.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from tinyagentos.containers import (
    exec_in_container, snapshot_create, snapshot_list, snapshot_delete,
)

logger = logging.getLogger(__name__)

SNAPSHOT_PREFIX = "pre-framework-update-"
UPDATE_DEADLINE_SECONDS = 120


async def _prune_old_snapshots(container: str, *, keep: int) -> None:
    """Keep the `keep` most recent pre-framework-update-* snapshots.
    `snapshot_list` returns newest first, so we delete the tail."""
    snaps = await snapshot_list(container, prefix=SNAPSHOT_PREFIX)
    for extra in snaps[keep:]:
        await snapshot_delete(container, extra["name"])


async def _wait_for_bootstrap_ping(
    agent: dict, *, started_at: int, deadline_seconds: int = UPDATE_DEADLINE_SECONDS,
) -> bool:
    """Poll `agent['bootstrap_last_seen_at']` every 500 ms. Returns True the
    first time it exceeds `started_at` (meaning the bridge has called
    `/api/openclaw/bootstrap` since the update started). False on deadline.
    """
    deadline = time.time() + deadline_seconds
    while time.time() < deadline:
        last = agent.get("bootstrap_last_seen_at") or 0
        if last > started_at:
            return True
        await asyncio.sleep(0.5)
    return False
