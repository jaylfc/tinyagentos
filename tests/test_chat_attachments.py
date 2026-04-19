import json
import pytest
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
