import json
import os
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from tinyagentos.chat.message_store import ChatMessageStore


@pytest.mark.asyncio
async def test_send_message_persists_attachments(tmp_path):
    store = ChatMessageStore(tmp_path / "msgs.db")
    await store.init()
    atts = [
        {"filename": "screenshot.png", "mime_type": "image/png",
         "size": 312456, "url": "/api/chat/files/abc-screenshot.png",
         "source": "disk"},
    ]
    msg = await store.send_message(
        channel_id="c1", author_id="user", author_type="user",
        content="look", content_type="text", state="complete",
        metadata=None, attachments=atts,
    )
    assert msg["attachments"] == atts


@pytest.mark.asyncio
async def test_send_message_defaults_attachments_to_empty_list(tmp_path):
    store = ChatMessageStore(tmp_path / "msgs.db")
    await store.init()
    msg = await store.send_message(
        channel_id="c1", author_id="user", author_type="user",
        content="plain", content_type="text", state="complete",
        metadata=None,
    )
    assert msg["attachments"] == []


@pytest.mark.asyncio
async def test_get_message_round_trips_attachments(tmp_path):
    store = ChatMessageStore(tmp_path / "msgs.db")
    await store.init()
    atts = [{"filename": "r.pdf", "mime_type": "application/pdf",
             "size": 500, "url": "/api/chat/files/r.pdf", "source": "workspace"}]
    msg = await store.send_message(
        channel_id="c1", author_id="user", author_type="user",
        content="see", content_type="text", state="complete",
        metadata=None, attachments=atts,
    )
    roundtripped = await store.get_message(msg["id"])
    assert roundtripped["attachments"] == atts


import yaml


def _make_from_path_app(tmp_path):
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


async def _authed_client(tmp_path):
    app = _make_from_path_app(tmp_path)
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
async def test_from_path_copies_workspace_file_and_returns_record(tmp_path):
    # seed a file in the user workspace
    ws = tmp_path / "agent-workspaces" / "user"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "report.md").write_text("# hi")

    app, client = await _authed_client(tmp_path)
    async with client:
        r = await client.post(
            "/api/chat/attachments/from-path",
            json={"path": "/workspaces/user/report.md", "source": "workspace"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["filename"] == "report.md"
        assert body["mime_type"] == "text/markdown"
        assert body["source"] == "workspace"
        assert body["url"].startswith("/api/chat/files/")
        # physical file exists
        stored_name = body["url"].rsplit("/", 1)[-1]
        assert (tmp_path / "chat-files" / stored_name).exists()


@pytest.mark.asyncio
async def test_from_path_rejects_traversal(tmp_path):
    app, client = await _authed_client(tmp_path)
    async with client:
        r = await client.post(
            "/api/chat/attachments/from-path",
            json={"path": "/workspaces/user/../../../etc/passwd", "source": "workspace"},
        )
        assert r.status_code in (400, 403)


@pytest.mark.asyncio
async def test_from_path_rejects_oversize(tmp_path):
    ws = tmp_path / "agent-workspaces" / "user"
    ws.mkdir(parents=True, exist_ok=True)
    big = ws / "big.bin"
    big.write_bytes(b"0" * (101 * 1024 * 1024))  # 101 MB

    app, client = await _authed_client(tmp_path)
    async with client:
        r = await client.post(
            "/api/chat/attachments/from-path",
            json={"path": "/workspaces/user/big.bin", "source": "workspace"},
        )
        assert r.status_code in (413, 400)
        assert "too large" in r.json().get("error", "").lower()
