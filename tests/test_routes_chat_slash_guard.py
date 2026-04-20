"""Tests for the bare-slash guardrail in non-DM channels."""
import pytest
import yaml

from httpx import AsyncClient, ASGITransport
from tinyagentos.app import create_app


def _make_app(tmp_path):
    cfg = {
        "server": {"host": "0.0.0.0", "port": 6969},
        "backends": [],
        "qmd": {"url": "http://localhost:7832"},
        "agents": [],
        "metrics": {"poll_interval": 30, "retention_days": 30},
    }
    (tmp_path / "config.yaml").write_text(yaml.dump(cfg))
    (tmp_path / ".setup_complete").touch()
    return create_app(data_dir=tmp_path)


async def _setup_client(tmp_path):
    app = _make_app(tmp_path)
    await app.state.chat_channels.init()
    await app.state.chat_messages.init()
    app.state.auth.setup_user("admin", "Test Admin", "", "testpass")
    rec = app.state.auth.find_user("admin")
    token = app.state.auth.create_session(user_id=rec["id"], long_lived=True)
    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"taos_session": token},
    )
    return app, client


@pytest.mark.asyncio
async def test_bare_slash_in_group_returns_400(tmp_path):
    # `/help` is intercepted in-app (taOS control command) so use a generic
    # slash command to exercise the guardrail path.
    app, client = await _setup_client(tmp_path)
    async with client:
        ch = await app.state.chat_channels.create_channel(
            name="g", type="group", description="", topic="",
            members=["user", "tom", "don"], settings={}, created_by="user",
        )
        ch_id = ch["id"] if isinstance(ch, dict) else ch
        r = await client.post(
            "/api/chat/messages",
            json={"channel_id": ch_id, "author_id": "user",
                  "author_type": "user", "content": "/clear",
                  "content_type": "text"},
        )
        assert r.status_code == 400
        assert "address an agent" in r.json()["error"]


@pytest.mark.asyncio
async def test_slash_with_mention_allowed(tmp_path):
    app, client = await _setup_client(tmp_path)
    async with client:
        ch = await app.state.chat_channels.create_channel(
            name="g", type="group", description="", topic="",
            members=["user", "tom"], settings={}, created_by="user",
        )
        ch_id = ch["id"] if isinstance(ch, dict) else ch
        r = await client.post(
            "/api/chat/messages",
            json={"channel_id": ch_id, "author_id": "user",
                  "author_type": "user", "content": "@tom /help",
                  "content_type": "text"},
        )
        assert r.status_code in (200, 201, 202)


@pytest.mark.asyncio
async def test_slash_with_at_all_allowed(tmp_path):
    app, client = await _setup_client(tmp_path)
    async with client:
        ch = await app.state.chat_channels.create_channel(
            name="g", type="group", description="", topic="",
            members=["user", "tom", "don"], settings={}, created_by="user",
        )
        ch_id = ch["id"] if isinstance(ch, dict) else ch
        r = await client.post(
            "/api/chat/messages",
            json={"channel_id": ch_id, "author_id": "user",
                  "author_type": "user", "content": "@all /help",
                  "content_type": "text"},
        )
        assert r.status_code in (200, 201, 202)


@pytest.mark.asyncio
async def test_slash_in_dm_allowed(tmp_path):
    app, client = await _setup_client(tmp_path)
    async with client:
        ch = await app.state.chat_channels.create_channel(
            name="dm", type="dm", description="", topic="",
            members=["user", "tom"], settings={}, created_by="user",
        )
        ch_id = ch["id"] if isinstance(ch, dict) else ch
        r = await client.post(
            "/api/chat/messages",
            json={"channel_id": ch_id, "author_id": "user",
                  "author_type": "user", "content": "/help",
                  "content_type": "text"},
        )
        assert r.status_code in (200, 201, 202)


@pytest.mark.asyncio
async def test_non_slash_in_group_allowed(tmp_path):
    app, client = await _setup_client(tmp_path)
    async with client:
        ch = await app.state.chat_channels.create_channel(
            name="g", type="group", description="", topic="",
            members=["user", "tom", "don"], settings={}, created_by="user",
        )
        ch_id = ch["id"] if isinstance(ch, dict) else ch
        r = await client.post(
            "/api/chat/messages",
            json={"channel_id": ch_id, "author_id": "user",
                  "author_type": "user", "content": "hello folks",
                  "content_type": "text"},
        )
        assert r.status_code in (200, 201, 202)
