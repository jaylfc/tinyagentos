"""Tests for chat HTTP routes."""
from __future__ import annotations

import pytest

from tinyagentos.chat.hub import ChatHub


async def _create_channel(client, name="general"):
    """Helper: create a chat channel via the channel store directly."""
    app = client._transport.app
    ch_store = app.state.chat_channels
    return await ch_store.create_channel(
        name=name, type="text", created_by="user"
    )


# ── POST /api/chat/messages ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_message(client):
    ch = await _create_channel(client)
    resp = await client.post("/api/chat/messages", json={
        "channel_id": ch["id"],
        "author_id": "agent-1",
        "author_type": "agent",
        "content": "Hello from agent",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"]
    assert body["content"] == "Hello from agent"
    assert body["channel_id"] == ch["id"]
    assert body["author_id"] == "agent-1"


@pytest.mark.asyncio
async def test_post_message_with_embeds(client):
    ch = await _create_channel(client)
    embeds = [{"title": "Test Embed", "description": "Some description"}]
    resp = await client.post("/api/chat/messages", json={
        "channel_id": ch["id"],
        "author_id": "agent-1",
        "content": "Message with embed",
        "embeds": embeds,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["embeds"] == embeds


@pytest.mark.asyncio
async def test_post_message_state_defaults_to_complete(client):
    ch = await _create_channel(client)
    resp = await client.post("/api/chat/messages", json={
        "channel_id": ch["id"],
        "author_id": "agent-1",
        "content": "Done",
    })
    assert resp.status_code == 200
    assert resp.json()["state"] == "complete"


@pytest.mark.asyncio
async def test_post_message_explicit_state(client):
    ch = await _create_channel(client)
    resp = await client.post("/api/chat/messages", json={
        "channel_id": ch["id"],
        "author_id": "agent-1",
        "content": "",
        "state": "streaming",
    })
    assert resp.status_code == 200
    assert resp.json()["state"] == "streaming"


# ── POST /api/chat/messages/{id}/delta ───────────────────────────────────────

@pytest.mark.asyncio
async def test_post_delta(client):
    ch = await _create_channel(client)
    create_resp = await client.post("/api/chat/messages", json={
        "channel_id": ch["id"],
        "author_id": "agent-1",
        "content": "",
        "state": "streaming",
    })
    msg_id = create_resp.json()["id"]

    resp = await client.post(f"/api/chat/messages/{msg_id}/delta", json={
        "channel_id": ch["id"],
        "delta": " world",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"


@pytest.mark.asyncio
async def test_post_delta_unknown_message(client):
    """Delta for non-existent message still returns 200 (broadcast is best-effort)."""
    resp = await client.post("/api/chat/messages/nonexistent/delta", json={
        "channel_id": "ch-x",
        "delta": "hi",
    })
    assert resp.status_code == 200


# ── POST /api/chat/messages/{id}/state ───────────────────────────────────────

@pytest.mark.asyncio
async def test_update_state(client):
    ch = await _create_channel(client)
    create_resp = await client.post("/api/chat/messages", json={
        "channel_id": ch["id"],
        "author_id": "agent-1",
        "content": "",
        "state": "streaming",
    })
    msg_id = create_resp.json()["id"]

    resp = await client.post(f"/api/chat/messages/{msg_id}/state", json={
        "state": "complete",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "updated"

    # Verify the state was persisted
    app = client._transport.app
    msg_store = app.state.chat_messages
    msg = await msg_store.get_message(msg_id)
    assert msg["state"] == "complete"


@pytest.mark.asyncio
async def test_update_state_unknown_message(client):
    """State update for non-existent message returns 200 (graceful noop)."""
    resp = await client.post("/api/chat/messages/nonexistent/state", json={
        "state": "error",
    })
    assert resp.status_code == 200


# ── Hub is wired into app.state ───────────────────────────────────────────────

def test_chat_hub_in_app_state(app):
    assert hasattr(app.state, "chat_hub")
    assert isinstance(app.state.chat_hub, ChatHub)
