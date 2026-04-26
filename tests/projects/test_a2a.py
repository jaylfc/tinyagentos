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
