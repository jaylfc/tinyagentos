"""Tests for the Zero-Loss Archive Layer (taOSmd)."""

import json
import time
import pytest
import pytest_asyncio
from tinyagentos.archive import (
    ArchiveStore,
    EVENT_CONVERSATION, EVENT_TOOL_CALL, EVENT_ERROR,
    EVENT_APP_USAGE, EVENT_CONTENT_VIEW, EVENT_SEARCH,
)


@pytest_asyncio.fixture
async def store(tmp_path):
    s = ArchiveStore(
        archive_dir=tmp_path / "archive",
        index_path=tmp_path / "archive-index.db",
    )
    await s.init()
    yield s
    await s.close()


# ------------------------------------------------------------------
# Recording
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_creates_jsonl_file(store, tmp_path):
    row_id = await store.record(
        EVENT_CONVERSATION,
        {"role": "user", "content": "Hello agent"},
        agent_name="research-agent",
        summary="User greeted agent",
    )
    assert row_id > 0
    # Check JSONL file exists
    files = list((tmp_path / "archive").rglob("*.jsonl"))
    assert len(files) == 1
    with open(files[0]) as f:
        line = json.loads(f.readline())
    assert line["event_type"] == EVENT_CONVERSATION
    assert line["data"]["content"] == "Hello agent"


@pytest.mark.asyncio
async def test_record_multiple_events(store):
    await store.record(EVENT_CONVERSATION, {"msg": "1"}, agent_name="a1")
    await store.record(EVENT_TOOL_CALL, {"tool": "search", "result": "found"}, agent_name="a1")
    await store.record(EVENT_ERROR, {"error": "timeout"}, agent_name="a1")
    events = await store.query()
    assert len(events) == 3


@pytest.mark.asyncio
async def test_record_with_app_id(store):
    await store.record(EVENT_CONVERSATION, {"msg": "test"}, app_id="reddit")
    events = await store.query(app_id="reddit")
    assert len(events) == 1


# ------------------------------------------------------------------
# User tracking opt-in
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_activity_blocked_by_default(store):
    row_id = await store.record(EVENT_CONTENT_VIEW, {"url": "https://reddit.com/r/test"})
    assert row_id == -1  # Not recorded
    events = await store.query()
    assert len(events) == 0


@pytest.mark.asyncio
async def test_user_activity_enabled(store):
    await store.set_user_tracking(True)
    assert store.user_tracking_enabled is True
    row_id = await store.record(EVENT_CONTENT_VIEW, {"url": "https://reddit.com/r/test"})
    assert row_id > 0
    events = await store.query()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_user_tracking_persists(store):
    await store.set_user_tracking(True)
    assert store.user_tracking_enabled is True
    await store.set_user_tracking(False)
    assert store.user_tracking_enabled is False


@pytest.mark.asyncio
async def test_system_events_always_recorded(store):
    # System events are NOT user activity — they always record
    row_id = await store.record(EVENT_CONVERSATION, {"msg": "hello"}, agent_name="agent")
    assert row_id > 0


@pytest.mark.asyncio
async def test_app_usage_blocked_without_opt_in(store):
    row_id = await store.record(EVENT_APP_USAGE, {"app": "reddit", "action": "open"})
    assert row_id == -1


@pytest.mark.asyncio
async def test_search_tracking_blocked_without_opt_in(store):
    row_id = await store.record(EVENT_SEARCH, {"query": "taOS docs"})
    assert row_id == -1


# ------------------------------------------------------------------
# Querying
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_by_event_type(store):
    await store.record(EVENT_CONVERSATION, {"msg": "1"})
    await store.record(EVENT_TOOL_CALL, {"tool": "search"})
    await store.record(EVENT_CONVERSATION, {"msg": "2"})
    convos = await store.query(event_type=EVENT_CONVERSATION)
    assert len(convos) == 2
    tools = await store.query(event_type=EVENT_TOOL_CALL)
    assert len(tools) == 1


@pytest.mark.asyncio
async def test_query_by_agent(store):
    await store.record(EVENT_CONVERSATION, {"msg": "1"}, agent_name="agent-a")
    await store.record(EVENT_CONVERSATION, {"msg": "2"}, agent_name="agent-b")
    a_events = await store.query(agent_name="agent-a")
    assert len(a_events) == 1


@pytest.mark.asyncio
async def test_query_with_search(store):
    await store.record(EVENT_CONVERSATION, {"content": "How do I use Docker?"}, summary="Docker question")
    await store.record(EVENT_CONVERSATION, {"content": "What is taOS?"}, summary="taOS question")
    results = await store.query(search="Docker")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_query_with_time_range(store):
    past = time.time() - 100
    await store.record(EVENT_CONVERSATION, {"msg": "recent"})
    results = await store.query(since=past)
    assert len(results) == 1
    results = await store.query(until=past)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_query_limit_offset(store):
    for i in range(10):
        await store.record(EVENT_CONVERSATION, {"msg": f"msg-{i}"})
    page1 = await store.query(limit=5, offset=0)
    page2 = await store.query(limit=5, offset=5)
    assert len(page1) == 5
    assert len(page2) == 5
    assert page1[0]["id"] != page2[0]["id"]


@pytest.mark.asyncio
async def test_get_event(store):
    row_id = await store.record(EVENT_TOOL_CALL, {"tool": "search", "input": "query", "output": "results"})
    event = await store.get_event(row_id)
    assert event is not None
    assert event["event_type"] == EVENT_TOOL_CALL
    assert event["data"]["tool"] == "search"


@pytest.mark.asyncio
async def test_get_event_not_found(store):
    event = await store.get_event(99999)
    assert event is None


# ------------------------------------------------------------------
# Stats + Summary
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_count(store):
    await store.record(EVENT_CONVERSATION, {"msg": "1"})
    await store.record(EVENT_CONVERSATION, {"msg": "2"})
    await store.record(EVENT_TOOL_CALL, {"tool": "x"})
    assert await store.count() == 3
    assert await store.count(event_type=EVENT_CONVERSATION) == 2


@pytest.mark.asyncio
async def test_daily_summary(store):
    await store.record(EVENT_CONVERSATION, {"msg": "1"})
    await store.record(EVENT_TOOL_CALL, {"tool": "x"})
    await store.record(EVENT_TOOL_CALL, {"tool": "y"})
    summary = await store.daily_summary()
    assert summary["total"] == 3
    assert summary["events"][EVENT_CONVERSATION] == 1
    assert summary["events"][EVENT_TOOL_CALL] == 2


@pytest.mark.asyncio
async def test_stats(store):
    await store.record(EVENT_CONVERSATION, {"msg": "1"})
    stats = await store.stats()
    assert stats["total_events"] == 1
    assert stats["active_files"] >= 1
    assert stats["disk_usage_mb"] >= 0
    assert stats["user_tracking_enabled"] is False


# ------------------------------------------------------------------
# Export
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_export_day(store):
    await store.record(EVENT_CONVERSATION, {"msg": "hello"})
    await store.record(EVENT_TOOL_CALL, {"tool": "search"})
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    events = await store.export_day(today)
    assert len(events) == 2
    assert events[0]["event_type"] == EVENT_CONVERSATION
