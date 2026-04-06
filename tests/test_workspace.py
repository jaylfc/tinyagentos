from __future__ import annotations

import pytest
import pytest_asyncio

from tinyagentos.agent_messages import AgentMessageStore


@pytest_asyncio.fixture
async def msg_store(tmp_path):
    store = AgentMessageStore(tmp_path / "messages.db")
    await store.init()
    yield store
    await store.close()


@pytest.mark.asyncio
class TestAgentMessageStore:
    async def test_send_and_get(self, msg_store):
        msg_id = await msg_store.send("naira", "kira", "Hello from Naira!")
        assert msg_id is not None
        messages = await msg_store.get_messages("naira")
        assert len(messages) == 1
        assert messages[0]["from"] == "naira"
        assert messages[0]["to"] == "kira"
        assert messages[0]["message"] == "Hello from Naira!"

    async def test_get_messages_both_directions(self, msg_store):
        await msg_store.send("naira", "kira", "Hi Kira")
        await msg_store.send("kira", "naira", "Hi Naira")
        messages = await msg_store.get_messages("naira")
        assert len(messages) == 2

    async def test_get_conversation(self, msg_store):
        await msg_store.send("naira", "kira", "msg1")
        await msg_store.send("kira", "naira", "msg2")
        await msg_store.send("naira", "zara", "msg3")  # different conversation
        convo = await msg_store.get_conversation("naira", "kira")
        assert len(convo) == 2
        # Ordered by timestamp ASC
        assert convo[0]["message"] == "msg1"
        assert convo[1]["message"] == "msg2"

    async def test_unread_count(self, msg_store):
        await msg_store.send("naira", "kira", "Read me!")
        await msg_store.send("naira", "kira", "And me!")
        count = await msg_store.unread_count("kira")
        assert count == 2

    async def test_mark_read(self, msg_store):
        await msg_store.send("naira", "kira", "Read me!")
        await msg_store.mark_read("kira")
        count = await msg_store.unread_count("kira")
        assert count == 0

    async def test_unread_count_only_to_agent(self, msg_store):
        await msg_store.send("naira", "kira", "To kira")
        await msg_store.send("kira", "naira", "From kira")
        # Naira should have 1 unread (the one from kira)
        assert await msg_store.unread_count("naira") == 1
        # Kira should have 1 unread (the one from naira)
        assert await msg_store.unread_count("kira") == 1

    async def test_send_with_tool_calls(self, msg_store):
        tools = [{"name": "search", "args": {"q": "test"}}]
        results = [{"output": "found it"}]
        msg_id = await msg_store.send(
            "naira", "kira", "Using tools",
            tool_calls=tools, tool_results=results,
            metadata={"intent": "research"},
        )
        messages = await msg_store.get_messages("naira")
        assert messages[0]["tool_calls"] == tools
        assert messages[0]["tool_results"] == results
        assert messages[0]["metadata"] == {"intent": "research"}

    async def test_get_messages_limit(self, msg_store):
        for i in range(10):
            await msg_store.send("naira", "kira", f"msg{i}")
        messages = await msg_store.get_messages("naira", limit=3)
        assert len(messages) == 3


# --- Route tests ---

@pytest.mark.asyncio
async def test_workspace_page_renders(client):
    resp = await client.get("/agents/test-agent/workspace")
    assert resp.status_code == 200
    assert "test-agent" in resp.text
    assert "Workspace" in resp.text
    assert "Messages" in resp.text
    assert "Files" in resp.text


@pytest.mark.asyncio
async def test_workspace_page_404_for_unknown_agent(client):
    resp = await client.get("/agents/nonexistent/workspace")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_workspace_messages_page_renders(client):
    resp = await client.get("/agents/test-agent/workspace/messages")
    assert resp.status_code == 200
    assert "Messages" in resp.text


@pytest.mark.asyncio
async def test_api_agent_messages_empty(client):
    resp = await client.get("/api/agents/test-agent/messages")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_api_send_and_list_messages(client):
    resp = await client.post("/api/agents/test-agent/messages", json={
        "from_agent": "other-agent",
        "message": "Hello test-agent!",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "sent"

    resp = await client.get("/api/agents/test-agent/messages")
    assert resp.status_code == 200
    messages = resp.json()
    assert len(messages) == 1
    assert messages[0]["from"] == "other-agent"
    assert messages[0]["to"] == "test-agent"
    assert messages[0]["message"] == "Hello test-agent!"


@pytest.mark.asyncio
async def test_api_agent_files_empty(client):
    resp = await client.get("/api/agents/test-agent/files")
    assert resp.status_code == 200
    assert resp.json() == []
