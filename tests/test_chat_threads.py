import pytest
import yaml
from httpx import AsyncClient, ASGITransport
from tinyagentos.chat.message_store import ChatMessageStore


@pytest.mark.asyncio
async def test_get_thread_messages_returns_replies_oldest_first(tmp_path):
    store = ChatMessageStore(tmp_path / "msgs.db")
    await store.init()
    parent = await store.send_message(
        channel_id="c1", author_id="user", author_type="user",
        content="parent", content_type="text", state="complete", metadata=None,
    )
    r1 = await store.send_message(
        channel_id="c1", author_id="tom", author_type="agent",
        content="r1", content_type="text", state="complete", metadata=None,
        thread_id=parent["id"],
    )
    r2 = await store.send_message(
        channel_id="c1", author_id="don", author_type="agent",
        content="r2", content_type="text", state="complete", metadata=None,
        thread_id=parent["id"],
    )
    msgs = await store.get_thread_messages(channel_id="c1", parent_id=parent["id"], limit=20)
    assert [m["id"] for m in msgs] == [r1["id"], r2["id"]]
    # parent is NOT included
    assert all(m["id"] != parent["id"] for m in msgs)


def _make_threads_app(tmp_path):
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


async def _authed_thread_client(tmp_path):
    """Create app + authenticated client with DB stores pre-initialized.
    ASGITransport in httpx 0.28 does not fire lifespan events, so we init
    the chat stores manually before returning."""
    app = _make_threads_app(tmp_path)
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
async def test_get_thread_messages_endpoint(tmp_path):
    app, client = await _authed_thread_client(tmp_path)
    async with client:
        ch_r = await client.post(
            "/api/chat/channels",
            json={"name": "g", "type": "group", "description": "", "topic": "",
                  "members": ["user", "tom"], "created_by": "user"},
        )
        assert ch_r.status_code in (200, 201), ch_r.json()
        ch_id = ch_r.json()["id"]

        # post parent message
        r = await client.post(
            "/api/chat/messages",
            json={"channel_id": ch_id, "author_id": "user", "author_type": "user",
                  "content": "parent", "content_type": "text"},
        )
        assert r.status_code in (200, 201), r.json()
        parent_id = r.json()["id"]

        # post reply with thread_id
        r = await client.post(
            "/api/chat/messages",
            json={"channel_id": ch_id, "author_id": "user", "author_type": "user",
                  "content": "reply", "content_type": "text",
                  "thread_id": parent_id},
        )
        assert r.status_code in (200, 201), r.json()

        # fetch thread messages
        r = await client.get(f"/api/chat/channels/{ch_id}/threads/{parent_id}/messages")
        assert r.status_code == 200
        body = r.json()
        assert len(body["messages"]) == 1
        assert body["messages"][0]["content"] == "reply"
