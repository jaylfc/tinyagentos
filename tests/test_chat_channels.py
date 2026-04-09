"""Tests for ChatChannelStore — 14 tests."""
from __future__ import annotations

import pytest
import pytest_asyncio

from tinyagentos.chat.channel_store import ChatChannelStore
from tinyagentos.chat.message_store import ChatMessageStore


@pytest_asyncio.fixture
async def store(tmp_path):
    s = ChatChannelStore(tmp_path / "chat.db")
    await s.init()
    yield s
    await s.close()


@pytest_asyncio.fixture
async def store_with_messages(tmp_path):
    """Channel store and a message store sharing the same DB file."""
    db_path = tmp_path / "chat.db"
    cs = ChatChannelStore(db_path)
    await cs.init()
    ms = ChatMessageStore(db_path)
    await ms.init()
    yield cs, ms
    await ms.close()
    await cs.close()


# ── helpers ───────────────────────────────────────────────────────────────────

async def _create(store, name="general", type="text", created_by="user1", **kw):
    return await store.create_channel(name=name, type=type, created_by=created_by, **kw)


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_channel(store):
    ch = await _create(store)
    assert ch["id"]
    assert ch["name"] == "general"
    assert ch["type"] == "text"
    assert ch["created_by"] == "user1"
    assert ch["members"] == []
    assert ch["settings"] == {}


@pytest.mark.asyncio
async def test_get_channel(store):
    ch = await _create(store)
    fetched = await store.get_channel(ch["id"])
    assert fetched["id"] == ch["id"]
    assert fetched["name"] == "general"


@pytest.mark.asyncio
async def test_get_channel_missing(store):
    result = await store.get_channel("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_list_channels_all(store):
    await _create(store, name="ch1")
    await _create(store, name="ch2")
    channels = await store.list_channels()
    assert len(channels) == 2
    names = {c["name"] for c in channels}
    assert "ch1" in names
    assert "ch2" in names


@pytest.mark.asyncio
async def test_list_channels_for_member(store):
    ch1 = await _create(store, name="ch1", members=["alice", "bob"])
    ch2 = await _create(store, name="ch2", members=["bob"])
    ch3 = await _create(store, name="ch3", members=["charlie"])
    result = await store.list_channels(member_id="alice")
    ids = {c["id"] for c in result}
    assert ch1["id"] in ids
    assert ch2["id"] not in ids
    assert ch3["id"] not in ids


@pytest.mark.asyncio
async def test_create_dm_channel(store):
    ch = await _create(store, name="dm-alice-bob", type="dm", members=["alice", "bob"])
    assert ch["type"] == "dm"
    assert "alice" in ch["members"]
    assert "bob" in ch["members"]


@pytest.mark.asyncio
async def test_create_group_channel(store):
    members = ["alice", "bob", "charlie"]
    ch = await _create(store, name="project-group", type="group", members=members)
    assert ch["type"] == "group"
    assert len(ch["members"]) == 3


@pytest.mark.asyncio
async def test_create_thread_channel(store):
    ch = await _create(store, name="thread-123", type="thread")
    assert ch["type"] == "thread"


@pytest.mark.asyncio
async def test_update_channel(store):
    ch = await _create(store, name="old-name")
    await store.update_channel(ch["id"], name="new-name", description="Updated desc", topic="New topic")
    updated = await store.get_channel(ch["id"])
    assert updated["name"] == "new-name"
    assert updated["description"] == "Updated desc"
    assert updated["topic"] == "New topic"


@pytest.mark.asyncio
async def test_delete_channel(store):
    ch = await _create(store)
    deleted = await store.delete_channel(ch["id"])
    assert deleted is True
    assert await store.get_channel(ch["id"]) is None


@pytest.mark.asyncio
async def test_add_member(store):
    ch = await _create(store, members=["alice"])
    await store.add_member(ch["id"], "bob")
    updated = await store.get_channel(ch["id"])
    assert "bob" in updated["members"]
    assert "alice" in updated["members"]
    # Adding duplicate should not duplicate
    await store.add_member(ch["id"], "bob")
    updated2 = await store.get_channel(ch["id"])
    assert updated2["members"].count("bob") == 1


@pytest.mark.asyncio
async def test_remove_member(store):
    ch = await _create(store, members=["alice", "bob"])
    await store.remove_member(ch["id"], "bob")
    updated = await store.get_channel(ch["id"])
    assert "bob" not in updated["members"]
    assert "alice" in updated["members"]


@pytest.mark.asyncio
async def test_update_read_position(store):
    ch = await _create(store)
    await store.update_read_position("alice", ch["id"], "msg_abc")
    # Should not raise; calling again should update
    await store.update_read_position("alice", ch["id"], "msg_xyz")


@pytest.mark.asyncio
async def test_get_unread_counts(store_with_messages):
    cs, ms = store_with_messages
    ch = await cs.create_channel(name="general", type="text", created_by="alice", members=["alice", "bob"])

    # Send 2 messages first
    m1 = await ms.send_message(ch["id"], "alice", "user", "msg1")
    m2 = await ms.send_message(ch["id"], "alice", "user", "msg2")

    # Bob hasn't read anything — should see 2 unread
    counts = await cs.get_unread_counts("bob")
    assert counts[ch["id"]] == 2

    # Bob marks position at m2 (records current time)
    await cs.update_read_position("bob", ch["id"], m2["id"])

    # Send m3 AFTER the read position was set
    m3 = await ms.send_message(ch["id"], "alice", "user", "msg3")

    counts = await cs.get_unread_counts("bob")
    # m3 was sent after the read position timestamp
    assert counts[ch["id"]] >= 1


@pytest.mark.asyncio
async def test_update_last_message_at(store):
    ch = await _create(store)
    assert ch["last_message_at"] is None
    await store.update_last_message_at(ch["id"])
    updated = await store.get_channel(ch["id"])
    assert updated["last_message_at"] is not None
