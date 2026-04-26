"""Per-project A2A (agent-to-agent) coordination channel.

Owns the invariant that every active project has exactly one chat channel
with `name="a2a"`, `type="group"`, `settings.kind="a2a"`. Single source of
truth: `ensure_a2a_channel`. Called from project route hooks and from the
startup backfill.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

A2A_NAME = "a2a"
A2A_TYPE = "group"
A2A_KIND = "a2a"

# Per-project lock so concurrent ensure_a2a_channel calls (e.g. simultaneous
# add_member requests during backfill) serialize on the read-modify-write of
# channel members. Without this, two callers can each compute a stale member
# diff and clobber each other's add/remove operations.
_A2A_LOCKS: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def _find_a2a_channels(channel_store, project_id: str) -> list[dict]:
    """Return all of the project's A2A channel rows, oldest-first.

    Identification: project_id matches AND settings.kind == "a2a".
    The store already returns rows ordered by created_at ASC, so the first
    element of the returned list is the canonical A2A channel.
    """
    channels = await channel_store.list_channels(project_id=project_id)
    return [
        ch for ch in channels
        if (ch.get("settings") or {}).get("kind") == A2A_KIND
    ]


async def ensure_a2a_channel(channel_store, project_store, project_id: str) -> dict:
    """Create the A2A channel for project_id if missing, sync its members
    to the project's current native+clone members, return the channel row.

    Idempotent. Serialized per project_id via _A2A_LOCKS to prevent racing
    member-sync diffs when multiple callers fire concurrently.
    """
    async with _A2A_LOCKS[project_id]:
        project_members = await project_store.list_members(project_id)
        expected = {m["member_id"] for m in project_members}

        matches = await _find_a2a_channels(channel_store, project_id)
        if not matches:
            project = await project_store.get_project(project_id)
            created_by = project.get("created_by", "system") if project else "system"
            return await channel_store.create_channel(
                name=A2A_NAME,
                type=A2A_TYPE,
                created_by=created_by,
                members=sorted(expected),
                description="Agent coordination channel.",
                settings={"kind": A2A_KIND},
                project_id=project_id,
            )

        # Reconcile duplicates: oldest is canonical, archive the rest.
        # Defensive: pre-lock data, manual DB tampering, or migrations could
        # have produced more than one A2A channel for a project.
        existing = matches[0]
        for dup in matches[1:]:
            logger.warning(
                "a2a duplicate channel %s for project %s — archiving",
                dup.get("id"), project_id,
            )
            await channel_store.set_settings(dup["id"], {"archived": True})

        current = set(existing.get("members") or [])
        if current == expected:
            return existing

        to_add = expected - current
        to_remove = current - expected
        for slug in sorted(to_add):
            await channel_store.add_member(existing["id"], slug)
        for slug in sorted(to_remove):
            await channel_store.remove_member(existing["id"], slug)
        return await channel_store.get_channel(existing["id"])


async def backfill_all(channel_store, project_store) -> int:
    """Call ensure_a2a_channel for every active project. Returns count synced.

    Per-project failures are logged and do not stop the loop.
    """
    projects = await project_store.list_projects(status="active")
    count = 0
    for p in projects:
        try:
            await ensure_a2a_channel(channel_store, project_store, p["id"])
            count += 1
        except Exception:
            logger.exception("a2a backfill failed for project %s", p.get("id"))
    return count
