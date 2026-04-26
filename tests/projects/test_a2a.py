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
