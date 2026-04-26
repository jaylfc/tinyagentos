from __future__ import annotations

import pytest
import pytest_asyncio

from tinyagentos.chat.channel_store import ChatChannelStore
from tinyagentos.projects.a2a import (
    A2A_KIND,
    A2A_NAME,
    A2A_TYPE,
    backfill_all,
    ensure_a2a_channel,
)
from tinyagentos.projects.project_store import ProjectStore


@pytest_asyncio.fixture
async def stores(tmp_path):
    project_store = ProjectStore(tmp_path / "projects.db")
    await project_store.init()
    channel_store = ChatChannelStore(tmp_path / "chat.db")
    await channel_store.init()
    yield project_store, channel_store
    await channel_store.close()
    await project_store.close()


@pytest.mark.asyncio
async def test_ensure_creates_channel_when_missing(stores):
    project_store, channel_store = stores
    p = await project_store.create_project(name="Acme", slug="acme", created_by="u1")

    ch = await ensure_a2a_channel(channel_store, project_store, p["id"])

    assert ch["name"] == A2A_NAME
    assert ch["type"] == A2A_TYPE
    assert ch["project_id"] == p["id"]
    assert ch["settings"].get("kind") == A2A_KIND
    assert ch["members"] == []


@pytest.mark.asyncio
async def test_ensure_is_idempotent(stores):
    project_store, channel_store = stores
    p = await project_store.create_project(name="Acme", slug="acme2", created_by="u1")

    ch1 = await ensure_a2a_channel(channel_store, project_store, p["id"])
    ch2 = await ensure_a2a_channel(channel_store, project_store, p["id"])

    assert ch1["id"] == ch2["id"]
    all_channels = await channel_store.list_channels(project_id=p["id"])
    a2a = [c for c in all_channels if (c.get("settings") or {}).get("kind") == "a2a"]
    assert len(a2a) == 1


@pytest.mark.asyncio
async def test_ensure_syncs_members_added_after_creation(stores):
    project_store, channel_store = stores
    p = await project_store.create_project(name="P", slug="sync-add", created_by="u1")
    await ensure_a2a_channel(channel_store, project_store, p["id"])

    await project_store.add_member(p["id"], "agentA", member_kind="native")
    await project_store.add_member(p["id"], "agentB", member_kind="native")
    ch = await ensure_a2a_channel(channel_store, project_store, p["id"])

    assert sorted(ch["members"]) == ["agentA", "agentB"]


@pytest.mark.asyncio
async def test_ensure_syncs_members_on_remove(stores):
    project_store, channel_store = stores
    p = await project_store.create_project(name="P", slug="sync-rm", created_by="u1")
    await project_store.add_member(p["id"], "agentA", member_kind="native")
    await project_store.add_member(p["id"], "agentB", member_kind="native")
    await ensure_a2a_channel(channel_store, project_store, p["id"])

    await project_store.remove_member(p["id"], "agentA")
    ch = await ensure_a2a_channel(channel_store, project_store, p["id"])

    assert ch["members"] == ["agentB"]


@pytest.mark.asyncio
async def test_ensure_no_op_when_members_match(stores):
    project_store, channel_store = stores
    p = await project_store.create_project(name="P", slug="sync-same", created_by="u1")
    await project_store.add_member(p["id"], "agentA", member_kind="native")
    ch1 = await ensure_a2a_channel(channel_store, project_store, p["id"])
    ch2 = await ensure_a2a_channel(channel_store, project_store, p["id"])
    assert ch1["members"] == ch2["members"] == ["agentA"]


@pytest.mark.asyncio
async def test_backfill_creates_channels_for_all_active_projects(stores):
    project_store, channel_store = stores
    p1 = await project_store.create_project(name="P1", slug="bf1", created_by="u1")
    p2 = await project_store.create_project(name="P2", slug="bf2", created_by="u1")
    p3 = await project_store.create_project(name="P3", slug="bf3", created_by="u1")
    await project_store.set_status(p3["id"], "archived")

    count = await backfill_all(channel_store, project_store)

    assert count == 2
    assert await _has_a2a(channel_store, p1["id"])
    assert await _has_a2a(channel_store, p2["id"])
    assert not await _has_a2a(channel_store, p3["id"])


async def _has_a2a(channel_store, project_id: str) -> bool:
    chans = await channel_store.list_channels(project_id=project_id)
    return any((c.get("settings") or {}).get("kind") == "a2a" for c in chans)


@pytest.mark.asyncio
async def test_backfill_is_idempotent(stores):
    """Calling backfill twice is a no-op the second time."""
    project_store, channel_store = stores
    p = await project_store.create_project(name="P", slug="bf-idem", created_by="u1")

    n1 = await backfill_all(channel_store, project_store)
    n2 = await backfill_all(channel_store, project_store)

    assert n1 == 1 and n2 == 1
    chans = await channel_store.list_channels(project_id=p["id"])
    a2a = [c for c in chans if (c.get("settings") or {}).get("kind") == "a2a"]
    assert len(a2a) == 1


@pytest.mark.asyncio
async def test_ensure_archives_duplicate_a2a_channels(stores):
    """Defensive: if duplicate A2A channels exist (race / migration / manual
    insert), the oldest is canonical and the rest are archived."""
    project_store, channel_store = stores
    p = await project_store.create_project(name="P", slug="dup", created_by="u1")

    canonical = await ensure_a2a_channel(channel_store, project_store, p["id"])
    duplicate = await channel_store.create_channel(
        name=A2A_NAME,
        type=A2A_TYPE,
        created_by="u1",
        members=[],
        settings={"kind": A2A_KIND},
        project_id=p["id"],
    )

    result = await ensure_a2a_channel(channel_store, project_store, p["id"])

    assert result["id"] == canonical["id"]
    dup_after = await channel_store.get_channel(duplicate["id"])
    assert (dup_after.get("settings") or {}).get("archived") is True
    active = await channel_store.list_channels(project_id=p["id"], archived=False)
    a2a_active = [c for c in active if (c.get("settings") or {}).get("kind") == "a2a"]
    assert len(a2a_active) == 1
    assert a2a_active[0]["id"] == canonical["id"]
