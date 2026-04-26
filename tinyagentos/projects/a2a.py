"""Per-project A2A (agent-to-agent) coordination channel.

Owns the invariant that every active project has exactly one chat channel
with `name="a2a"`, `type="group"`, `settings.kind="a2a"`. Single source of
truth: `ensure_a2a_channel`. Called from project route hooks and from the
startup backfill.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

A2A_NAME = "a2a"
A2A_TYPE = "group"
A2A_KIND = "a2a"


async def _find_a2a_channel(channel_store, project_id: str) -> dict | None:
    """Return the project's A2A channel row, or None.

    Identification: project_id matches AND settings.kind == "a2a".
    """
    channels = await channel_store.list_channels(project_id=project_id)
    for ch in channels:
        if (ch.get("settings") or {}).get("kind") == A2A_KIND:
            return ch
    return None


async def ensure_a2a_channel(channel_store, project_store, project_id: str) -> dict:
    """Create the A2A channel for project_id if missing.

    Idempotent: safe to call repeatedly. (Member sync added in Task 3.)
    """
    existing = await _find_a2a_channel(channel_store, project_id)
    if existing is not None:
        return existing
    project = await project_store.get_project(project_id)
    created_by = project.get("created_by", "system") if project else "system"
    return await channel_store.create_channel(
        name=A2A_NAME,
        type=A2A_TYPE,
        created_by=created_by,
        members=[],
        description="Agent coordination channel.",
        settings={"kind": A2A_KIND},
        project_id=project_id,
    )


async def backfill_all(channel_store, project_store) -> int:
    """Stub — implemented in Task 4."""
    return 0
