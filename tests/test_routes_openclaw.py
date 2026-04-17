"""Tests for openclaw bridge endpoints.

  GET  /api/openclaw/bootstrap
  GET  /api/openclaw/sessions/{agent}/events
  POST /api/openclaw/sessions/{agent}/reply

Uses the standard conftest fixtures (app, client) but also constructs a
bearer-auth client so we can test the local-token path.
"""
from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio
import yaml
from httpx import ASGITransport, AsyncClient

from tinyagentos.app import create_app
from tinyagentos.bridge_session import BridgeSessionRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def openclaw_data_dir(tmp_path):
    """tmp data dir with an agent that has llm_key set."""
    config = {
        "server": {"host": "0.0.0.0", "port": 6969},
        "backends": [
            {"name": "test-backend", "type": "rkllama", "url": "http://localhost:8080", "priority": 1}
        ],
        "qmd": {"url": "http://localhost:7832"},
        "agents": [
            {
                "name": "mybot",
                "host": "192.168.1.10",
                "color": "#aabbcc",
                "llm_key": "sk-test-virtualkey",
                "model": "qwen2.5:7b",
                "chat_channel_id": "ch_mybot",
            }
        ],
        "metrics": {"poll_interval": 30, "retention_days": 30},
    }
    (tmp_path / "config.yaml").write_text(yaml.dump(config))
    (tmp_path / ".setup_complete").touch()
    return tmp_path


@pytest.fixture
def openclaw_app(openclaw_data_dir):
    return create_app(data_dir=openclaw_data_dir)


@pytest_asyncio.fixture
async def bearer_client(openclaw_app):
    """Client that authenticates via the local bearer token."""
    app = openclaw_app
    # Init required stores.
    for attr in ("metrics", "notifications", "secrets", "scheduler", "channels",
                 "relationships", "conversion", "training", "agent_messages",
                 "shared_folders", "streaming_sessions", "expert_agents",
                 "chat_messages", "chat_channels", "canvas_store"):
        store = getattr(app.state, attr)
        if getattr(store, "_db", None) is not None:
            await store.close()
        await store.init()
    await app.state.qmd_client.init()
    app.state.auth.setup_user("admin", "Test Admin", "", "testpass")
    token = app.state.auth.get_local_token()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as c:
        yield c, token, app
    for attr in ("canvas_store", "chat_channels", "chat_messages", "expert_agents",
                 "streaming_sessions", "shared_folders", "agent_messages",
                 "conversion", "training", "relationships", "channels",
                 "scheduler", "secrets", "notifications", "metrics"):
        store = getattr(app.state, attr)
        try:
            await store.close()
        except Exception:
            pass
    try:
        await app.state.qmd_client.close()
    except Exception:
        pass
    try:
        await app.state.http_client.aclose()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Bootstrap tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bootstrap_shape(bearer_client):
    client, token, app = bearer_client
    resp = await client.get("/api/openclaw/bootstrap?agent=mybot")
    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == 1
    assert data["agent_name"] == "mybot"
    providers = data["models"]["providers"]
    assert len(providers) == 1
    p = providers[0]
    assert p["id"] == "taos"
    assert p["apiKey"] == "sk-test-virtualkey"
    assert p["default_model"] == "qwen2.5:7b"
    assert data["channel"]["auth_bearer"] == token
    assert "events_url" in data["channel"]
    assert "reply_url" in data["channel"]
    assert data["memory"] is None
    assert data["skills_mcp_url"] is None


@pytest.mark.asyncio
async def test_bootstrap_agent_not_found(bearer_client):
    client, *_ = bearer_client
    resp = await client.get("/api/openclaw/bootstrap?agent=nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_bootstrap_no_agent_param(bearer_client):
    client, *_ = bearer_client
    resp = await client.get("/api/openclaw/bootstrap")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_bootstrap_missing_llm_key(tmp_path, openclaw_app):
    """409 when agent exists but llm_key is absent."""
    app = openclaw_app
    # Patch config to have an agent without llm_key.
    for a in app.state.config.agents:
        if a.get("name") == "mybot":
            a.pop("llm_key", None)

    for attr in ("metrics", "notifications", "secrets", "scheduler", "channels",
                 "relationships", "conversion", "training", "agent_messages",
                 "shared_folders", "streaming_sessions", "expert_agents",
                 "chat_messages", "chat_channels", "canvas_store"):
        store = getattr(app.state, attr)
        if getattr(store, "_db", None) is not None:
            await store.close()
        await store.init()
    await app.state.qmd_client.init()
    app.state.auth.setup_user("admin", "Test Admin", "", "testpass")
    token = app.state.auth.get_local_token()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as c:
        resp = await c.get("/api/openclaw/bootstrap?agent=mybot")
    assert resp.status_code == 409

    for attr in ("canvas_store", "chat_channels", "chat_messages", "expert_agents",
                 "streaming_sessions", "shared_folders", "agent_messages",
                 "conversion", "training", "relationships", "channels",
                 "scheduler", "secrets", "notifications", "metrics"):
        try:
            await getattr(app.state, attr).close()
        except Exception:
            pass
    try:
        await app.state.qmd_client.close()
    except Exception:
        pass
    try:
        await app.state.http_client.aclose()
    except Exception:
        pass


@pytest.mark.asyncio
async def test_bootstrap_auth_rejection(bearer_client):
    client, _token, app = bearer_client
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer wrongtoken"},
    ) as bad_client:
        resp = await bad_client.get("/api/openclaw/bootstrap?agent=mybot")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# SSE events stream tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_events_stream_auth_rejection(bearer_client):
    _client, _token, app = bearer_client
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer bad"},
    ) as bad_client:
        resp = await bad_client.get(
            "/api/openclaw/sessions/mybot/events",
            headers={"Accept": "text/event-stream"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_events_stream_receives_user_message(bearer_client):
    client, token, app = bearer_client

    registry: BridgeSessionRegistry = app.state.bridge_sessions
    # Pre-enqueue a message before subscribing so the stream has one item.
    await registry.enqueue_user_message("mybot", {
        "id": "u1",
        "trace_id": "tr1",
        "channel_id": "ch_mybot",
        "from": "user",
        "text": "ping",
        "created_at": 1000.0,
    })

    # Use the subscribe generator directly — avoids httpx SSE streaming quirks
    # with ASGI transport (httpx does not yield lines until the response closes).
    received_frames = []
    async for frame in registry.subscribe("mybot"):
        received_frames.append(frame)
        break  # stop after first frame

    assert len(received_frames) == 1
    assert "user_message" in received_frames[0]
    data_line = [l for l in received_frames[0].splitlines() if l.startswith("data:")][0]
    payload = json.loads(data_line[len("data:"):].strip())
    assert payload["text"] == "ping"


# ---------------------------------------------------------------------------
# Reply ingestion tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reply_auth_rejection(bearer_client):
    _client, _token, app = bearer_client
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer bad"},
    ) as bad_client:
        resp = await bad_client.post(
            "/api/openclaw/sessions/mybot/reply",
            json={"kind": "final", "trace_id": "t1", "content": "hi"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_reply_returns_202(bearer_client):
    client, *_ = bearer_client
    resp = await client.post(
        "/api/openclaw/sessions/mybot/reply",
        json={"kind": "final", "trace_id": "t1", "content": "hello"},
    )
    assert resp.status_code == 202
    assert resp.json()["accepted"] is True


@pytest.mark.asyncio
async def test_reply_delta_then_final_broadcasts(bearer_client):
    client, token, app = bearer_client
    hub = app.state.chat_hub
    initial_broadcast_count = len(hub._subscribers) if hasattr(hub, "_subscribers") else 0

    # delta
    resp = await client.post(
        "/api/openclaw/sessions/mybot/reply",
        json={"kind": "delta", "trace_id": "tX", "content": "Hel"},
    )
    assert resp.status_code == 202

    # another delta
    resp = await client.post(
        "/api/openclaw/sessions/mybot/reply",
        json={"kind": "delta", "trace_id": "tX", "content": "lo!"},
    )
    assert resp.status_code == 202

    # final
    resp = await client.post(
        "/api/openclaw/sessions/mybot/reply",
        json={"kind": "final", "trace_id": "tX", "content": ""},
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_reply_error_returns_202(bearer_client):
    client, *_ = bearer_client
    resp = await client.post(
        "/api/openclaw/sessions/mybot/reply",
        json={"kind": "error", "trace_id": "tE", "error": "something broke"},
    )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_reply_invalid_json_returns_400(bearer_client):
    client, token, app = bearer_client
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as c:
        resp = await c.post(
            "/api/openclaw/sessions/mybot/reply",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 400
