"""Integration tests for slash-command interception in POST /api/chat/messages.

Posts messages with and without slash prefixes. The slash path must emit a
system message and NOT route to agents; normal messages must fall through as
before.
"""
from __future__ import annotations

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

async def _make_channel(client):
    app = client._transport.app
    store = app.state.chat_channels
    ch = await store.create_channel(
        name="slash-test", type="group", description="",
        topic="", members=["user"], settings={}, created_by="user",
    )
    return ch["id"] if isinstance(ch, dict) else ch


# ── /lively — known command ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_slash_lively_returns_handled_slash(client):
    ch_id = await _make_channel(client)
    resp = await client.post(
        "/api/chat/messages",
        json={
            "channel_id": ch_id,
            "author_id": "user",
            "author_type": "user",
            "content": "/lively",
            "content_type": "text",
        },
    )
    assert resp.status_code in (200, 202)
    body = resp.json()
    assert body.get("handled") == "slash"


@pytest.mark.asyncio
async def test_slash_lively_persists_system_message(client):
    ch_id = await _make_channel(client)
    await client.post(
        "/api/chat/messages",
        json={
            "channel_id": ch_id,
            "author_id": "user",
            "author_type": "user",
            "content": "/lively",
            "content_type": "text",
        },
    )
    app = client._transport.app
    msg_store = app.state.chat_messages
    messages = await msg_store.get_messages(ch_id)
    system_msgs = [m for m in messages if m.get("author_type") == "system"]
    assert len(system_msgs) >= 1
    assert "lively" in system_msgs[0]["content"]


@pytest.mark.asyncio
async def test_slash_lively_sets_response_mode(client):
    ch_id = await _make_channel(client)
    await client.post(
        "/api/chat/messages",
        json={
            "channel_id": ch_id,
            "author_id": "user",
            "author_type": "user",
            "content": "/lively",
            "content_type": "text",
        },
    )
    app = client._transport.app
    ch = await app.state.chat_channels.get_channel(ch_id)
    assert ch["settings"]["response_mode"] == "lively"


# ── /quiet — another known command ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_slash_quiet_sets_response_mode(client):
    ch_id = await _make_channel(client)
    resp = await client.post(
        "/api/chat/messages",
        json={
            "channel_id": ch_id,
            "author_id": "user",
            "author_type": "user",
            "content": "/quiet",
        },
    )
    assert resp.status_code in (200, 202)
    assert resp.json().get("handled") == "slash"
    ch = await client._transport.app.state.chat_channels.get_channel(ch_id)
    assert ch["settings"]["response_mode"] == "quiet"


# ── unknown slash — falls through to normal message ──────────────────────────

@pytest.mark.asyncio
async def test_unknown_slash_falls_through_to_text(client):
    ch_id = await _make_channel(client)
    resp = await client.post(
        "/api/chat/messages",
        json={
            "channel_id": ch_id,
            "author_id": "user",
            "author_type": "user",
            "content": "/foo not a command",
            "content_type": "text",
        },
    )
    assert resp.status_code in (200, 201, 202)
    body = resp.json()
    # Not handled as slash — should be a normal persisted message
    assert body.get("handled") != "slash"
    assert body.get("content") == "/foo not a command"


# ── non-slash message — normal path unaffected ───────────────────────────────

@pytest.mark.asyncio
async def test_normal_message_not_intercepted(client):
    ch_id = await _make_channel(client)
    resp = await client.post(
        "/api/chat/messages",
        json={
            "channel_id": ch_id,
            "author_id": "agent-1",
            "author_type": "agent",
            "content": "Hello world",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("handled") != "slash"
    assert body["content"] == "Hello world"


# ── slash command system message has author_type=system ──────────────────────

@pytest.mark.asyncio
async def test_slash_system_message_author(client):
    ch_id = await _make_channel(client)
    resp = await client.post(
        "/api/chat/messages",
        json={
            "channel_id": ch_id,
            "author_id": "user",
            "author_type": "user",
            "content": "/help",
        },
    )
    assert resp.status_code in (200, 202)
    body = resp.json()
    assert body.get("handled") == "slash"
    sys_msg = body.get("system_message", {})
    assert sys_msg.get("author_id") == "system"
    assert sys_msg.get("author_type") == "system"
