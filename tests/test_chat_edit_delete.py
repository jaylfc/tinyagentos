import pytest
import yaml
from httpx import AsyncClient, ASGITransport


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
    from tinyagentos.app import create_app
    return create_app(data_dir=tmp_path)


async def _authed_client(tmp_path, username="admin"):
    app = _make_app(tmp_path)
    await app.state.chat_channels.init()
    await app.state.chat_messages.init()
    app.state.auth.setup_user(username, f"{username} Name", "", "testpass")
    rec = app.state.auth.find_user(username)
    token = app.state.auth.create_session(user_id=rec["id"], long_lived=True)
    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"taos_session": token},
    )
    return app, client, rec


@pytest.mark.asyncio
async def test_edit_own_message_sets_edited_at(tmp_path):
    app, client, rec = await _authed_client(tmp_path)
    async with client:
        ch_r = await client.post(
            "/api/chat/channels",
            json={"name": "g", "type": "group", "description": "", "topic": "",
                  "members": ["user", "tom"], "created_by": "user"},
        )
        ch_id = ch_r.json()["id"]
        m_r = await client.post(
            "/api/chat/messages",
            json={"channel_id": ch_id, "author_id": rec["id"], "author_type": "user",
                  "content": "v1", "content_type": "text"},
        )
        msg_id = m_r.json()["id"]
        r = await client.patch(
            f"/api/chat/messages/{msg_id}",
            json={"content": "v2"},
        )
        assert r.status_code == 200, r.json()
        assert r.json()["content"] == "v2"
        assert r.json()["edited_at"] is not None


@pytest.mark.asyncio
async def test_edit_non_own_returns_403(tmp_path):
    app, client, _ = await _authed_client(tmp_path)
    async with client:
        ch_r = await client.post(
            "/api/chat/channels",
            json={"name": "g", "type": "group", "description": "", "topic": "",
                  "members": ["user", "tom"], "created_by": "user"},
        )
        ch_id = ch_r.json()["id"]
        m = await app.state.chat_messages.send_message(
            channel_id=ch_id, author_id="tom", author_type="agent", content="tom's",
        )
        r = await client.patch(f"/api/chat/messages/{m['id']}", json={"content": "hacked"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_edit_rejects_non_content_fields(tmp_path):
    app, client, rec = await _authed_client(tmp_path)
    async with client:
        ch_r = await client.post(
            "/api/chat/channels",
            json={"name": "g", "type": "group", "description": "", "topic": "",
                  "members": ["user", "tom"], "created_by": "user"},
        )
        ch_id = ch_r.json()["id"]
        m_r = await client.post(
            "/api/chat/messages",
            json={"channel_id": ch_id, "author_id": rec["id"], "author_type": "user",
                  "content": "x", "content_type": "text"},
        )
        r = await client.patch(
            f"/api/chat/messages/{m_r.json()['id']}",
            json={"content": "ok", "thread_id": "evil"},
        )
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_edit_deleted_message_returns_404(tmp_path):
    app, client, rec = await _authed_client(tmp_path)
    async with client:
        ch_r = await client.post(
            "/api/chat/channels",
            json={"name": "g", "type": "group", "description": "", "topic": "",
                  "members": ["user", "tom"], "created_by": "user"},
        )
        ch_id = ch_r.json()["id"]
        m_r = await client.post(
            "/api/chat/messages",
            json={"channel_id": ch_id, "author_id": rec["id"], "author_type": "user",
                  "content": "x", "content_type": "text"},
        )
        msg_id = m_r.json()["id"]
        await app.state.chat_messages.soft_delete_message(msg_id)
        r = await client.patch(f"/api/chat/messages/{msg_id}", json={"content": "y"})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_own_returns_204_and_sets_deleted_at(tmp_path):
    app, client, rec = await _authed_client(tmp_path)
    async with client:
        ch_r = await client.post(
            "/api/chat/channels",
            json={"name": "g", "type": "group", "description": "", "topic": "",
                  "members": ["user", "tom"], "created_by": "user"},
        )
        ch_id = ch_r.json()["id"]
        m_r = await client.post(
            "/api/chat/messages",
            json={"channel_id": ch_id, "author_id": rec["id"], "author_type": "user",
                  "content": "bye", "content_type": "text"},
        )
        msg_id = m_r.json()["id"]
        r = await client.delete(f"/api/chat/messages/{msg_id}")
        assert r.status_code == 204
        got = await app.state.chat_messages.get_message(msg_id)
        assert got["deleted_at"] is not None


@pytest.mark.asyncio
async def test_delete_non_own_returns_403(tmp_path):
    app, client, _ = await _authed_client(tmp_path)
    async with client:
        ch_r = await client.post(
            "/api/chat/channels",
            json={"name": "g", "type": "group", "description": "", "topic": "",
                  "members": ["user", "tom"], "created_by": "user"},
        )
        ch_id = ch_r.json()["id"]
        m = await app.state.chat_messages.send_message(
            channel_id=ch_id, author_id="tom", author_type="agent", content="tom's",
        )
        r = await client.delete(f"/api/chat/messages/{m['id']}")
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_idempotent(tmp_path):
    app, client, rec = await _authed_client(tmp_path)
    async with client:
        ch_r = await client.post(
            "/api/chat/channels",
            json={"name": "g", "type": "group", "description": "", "topic": "",
                  "members": ["user", "tom"], "created_by": "user"},
        )
        ch_id = ch_r.json()["id"]
        m_r = await client.post(
            "/api/chat/messages",
            json={"channel_id": ch_id, "author_id": rec["id"], "author_type": "user",
                  "content": "x", "content_type": "text"},
        )
        msg_id = m_r.json()["id"]
        r1 = await client.delete(f"/api/chat/messages/{msg_id}")
        r2 = await client.delete(f"/api/chat/messages/{msg_id}")
        assert r1.status_code == 204
        assert r2.status_code == 204
