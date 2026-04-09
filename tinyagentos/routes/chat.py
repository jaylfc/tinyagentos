from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket):
    await websocket.accept()
    user_id = "user"  # For now, single user. Auth integration in future.
    hub = websocket.app.state.chat_hub
    hub.connect(websocket, user_id)
    try:
        while True:
            data = json.loads(await websocket.receive_text())
            msg_type = data.get("type")

            if msg_type == "join":
                hub.join(websocket, data["channel_id"])

            elif msg_type == "leave":
                hub.leave(websocket, data["channel_id"])

            elif msg_type == "message":
                msg_store = websocket.app.state.chat_messages
                ch_store = websocket.app.state.chat_channels
                message = await msg_store.send_message(
                    channel_id=data["channel_id"],
                    author_id=user_id,
                    author_type="user",
                    content=data.get("content", ""),
                    content_type=data.get("content_type", "text"),
                    thread_id=data.get("thread_id"),
                    embeds=data.get("embeds"),
                    components=data.get("components"),
                    attachments=data.get("attachments"),
                    content_blocks=data.get("content_blocks"),
                    metadata=data.get("metadata"),
                )
                await ch_store.update_last_message_at(data["channel_id"])
                await hub.broadcast(data["channel_id"], {"type": "message", "seq": hub.next_seq(), **message})

            elif msg_type == "typing":
                hub.set_typing(data["channel_id"], user_id)
                await hub.broadcast(data["channel_id"], {
                    "type": "typing",
                    "seq": hub.next_seq(),
                    "channel_id": data["channel_id"],
                    "user_id": user_id,
                    "user_type": "user",
                })

            elif msg_type == "reaction":
                msg_store = websocket.app.state.chat_messages
                if data.get("action") == "remove":
                    await msg_store.remove_reaction(data["message_id"], data["emoji"], user_id)
                else:
                    await msg_store.add_reaction(data["message_id"], data["emoji"], user_id)
                msg = await msg_store.get_message(data["message_id"])
                if msg:
                    await hub.broadcast(msg["channel_id"], {
                        "type": "reaction_update",
                        "seq": hub.next_seq(),
                        "message_id": data["message_id"],
                        "reactions": msg["reactions"],
                    })

            elif msg_type == "edit":
                msg_store = websocket.app.state.chat_messages
                await msg_store.edit_message(data["message_id"], data["content"])
                msg = await msg_store.get_message(data["message_id"])
                if msg:
                    await hub.broadcast(msg["channel_id"], {
                        "type": "message_edit",
                        "seq": hub.next_seq(),
                        "message_id": data["message_id"],
                        "content": data["content"],
                        "edited_at": msg["edited_at"],
                    })

            elif msg_type == "delete":
                msg_store = websocket.app.state.chat_messages
                msg = await msg_store.get_message(data["message_id"])
                if msg:
                    channel_id = msg["channel_id"]
                    await msg_store.delete_message(data["message_id"])
                    await hub.broadcast(channel_id, {
                        "type": "message_delete",
                        "seq": hub.next_seq(),
                        "message_id": data["message_id"],
                        "channel_id": channel_id,
                    })

            elif msg_type == "mark_read":
                ch_store = websocket.app.state.chat_channels
                await ch_store.update_read_position(user_id, data["channel_id"], data["message_id"])

            elif msg_type == "component_action":
                await hub.broadcast(data.get("channel_id", ""), {
                    "type": "component_action",
                    "seq": hub.next_seq(),
                    "message_id": data["message_id"],
                    "action": data["action"],
                    "value": data.get("value"),
                    "user_id": user_id,
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Chat WS error: {e}")
    finally:
        hub.disconnect(websocket, user_id)


@router.post("/api/chat/messages")
async def post_message(request: Request):
    """Send a message via HTTP (used by agents and the agent-bridge)."""
    body = await request.json()
    msg_store = request.app.state.chat_messages
    ch_store = request.app.state.chat_channels
    hub = request.app.state.chat_hub

    message = await msg_store.send_message(
        channel_id=body["channel_id"],
        author_id=body["author_id"],
        author_type=body.get("author_type", "agent"),
        content=body.get("content", ""),
        content_type=body.get("content_type", "text"),
        thread_id=body.get("thread_id"),
        embeds=body.get("embeds"),
        components=body.get("components"),
        attachments=body.get("attachments"),
        content_blocks=body.get("content_blocks"),
        metadata=body.get("metadata"),
        state=body.get("state", "complete"),
    )
    await ch_store.update_last_message_at(body["channel_id"])
    await hub.broadcast(body["channel_id"], {"type": "message", "seq": hub.next_seq(), **message})
    return message


@router.post("/api/chat/messages/{message_id}/delta")
async def post_message_delta(request: Request, message_id: str):
    """Stream a token delta for an agent response. Used by framework adapters."""
    body = await request.json()
    hub = request.app.state.chat_hub
    channel_id = body.get("channel_id", "")
    await hub.broadcast(channel_id, {
        "type": "message_delta",
        "seq": hub.next_seq(),
        "message_id": message_id,
        "channel_id": channel_id,
        "delta": body.get("delta", ""),
    })
    return {"status": "sent"}


@router.post("/api/chat/messages/{message_id}/state")
async def update_message_state(request: Request, message_id: str):
    """Update message state (pending/streaming/complete/error)."""
    body = await request.json()
    msg_store = request.app.state.chat_messages
    hub = request.app.state.chat_hub
    await msg_store.update_state(message_id, body["state"])
    msg = await msg_store.get_message(message_id)
    if msg:
        await hub.broadcast(msg["channel_id"], {
            "type": "message_state",
            "seq": hub.next_seq(),
            "message_id": message_id,
            "state": body["state"],
        })
    return {"status": "updated"}


# ── Channel CRUD ──────────────────────────────────────────────────────────────

@router.get("/api/chat/channels")
async def list_channels(request: Request, member: str | None = None):
    ch_store = request.app.state.chat_channels
    channels = await ch_store.list_channels(member_id=member)
    return {"channels": channels}


@router.post("/api/chat/channels")
async def create_channel(request: Request):
    body = await request.json()
    ch_store = request.app.state.chat_channels
    channel = await ch_store.create_channel(
        name=body["name"],
        type=body.get("type", "topic"),
        created_by=body.get("created_by", "user"),
        members=body.get("members"),
        description=body.get("description", ""),
        topic=body.get("topic", ""),
    )
    return channel


@router.get("/api/chat/channels/{channel_id}")
async def get_channel(request: Request, channel_id: str):
    ch_store = request.app.state.chat_channels
    channel = await ch_store.get_channel(channel_id)
    if not channel:
        return JSONResponse({"error": "Channel not found"}, status_code=404)
    return channel


@router.put("/api/chat/channels/{channel_id}")
async def update_channel(request: Request, channel_id: str):
    body = await request.json()
    ch_store = request.app.state.chat_channels
    channel = await ch_store.get_channel(channel_id)
    if not channel:
        return JSONResponse({"error": "Channel not found"}, status_code=404)
    await ch_store.update_channel(
        channel_id,
        name=body.get("name"),
        description=body.get("description"),
        topic=body.get("topic"),
    )
    return {"status": "updated"}


@router.delete("/api/chat/channels/{channel_id}")
async def delete_channel(request: Request, channel_id: str):
    ch_store = request.app.state.chat_channels
    deleted = await ch_store.delete_channel(channel_id)
    if not deleted:
        return JSONResponse({"error": "Channel not found"}, status_code=404)
    return {"status": "deleted"}


@router.get("/api/chat/channels/{channel_id}/messages")
async def get_channel_messages(
    request: Request, channel_id: str, limit: int = 50, before: float | None = None
):
    msg_store = request.app.state.chat_messages
    messages = await msg_store.get_messages(channel_id, limit=limit, before=before)
    return {"messages": messages}


@router.post("/api/chat/channels/{channel_id}/members")
async def add_channel_member(request: Request, channel_id: str):
    body = await request.json()
    ch_store = request.app.state.chat_channels
    await ch_store.add_member(channel_id, body["member_id"])
    return {"status": "added"}


@router.delete("/api/chat/channels/{channel_id}/members/{member_id}")
async def remove_channel_member(request: Request, channel_id: str, member_id: str):
    ch_store = request.app.state.chat_channels
    await ch_store.remove_member(channel_id, member_id)
    return {"status": "removed"}


# ── File upload / serve ───────────────────────────────────────────────────────

@router.post("/api/chat/upload")
async def upload_file(request: Request, file: UploadFile = File(...), channel_id: str = ""):
    """Upload a file attachment for use in chat messages."""
    data_dir = request.app.state.config_path.parent
    upload_dir = data_dir / "chat-files"
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4().hex[:12]
    ext = Path(file.filename).suffix if file.filename else ""
    stored_name = f"{file_id}{ext}"
    dest = upload_dir / stored_name
    content = await file.read()
    dest.write_bytes(content)

    attachment = {
        "id": file_id,
        "filename": file.filename or "unnamed",
        "content_type": file.content_type or "application/octet-stream",
        "size": len(content),
        "url": f"/api/chat/files/{stored_name}",
    }
    return attachment


@router.get("/api/chat/files/{filename}")
async def serve_file(request: Request, filename: str):
    """Serve an uploaded chat file."""
    data_dir = request.app.state.config_path.parent
    file_path = data_dir / "chat-files" / filename
    if not file_path.exists() or not file_path.resolve().is_relative_to(
        (data_dir / "chat-files").resolve()
    ):
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(file_path)


# ── Search & unread ───────────────────────────────────────────────────────────

@router.get("/api/chat/search")
async def search_messages(
    request: Request, q: str = "", channel_id: str | None = None, limit: int = 20
):
    if not q or len(q) < 2:
        return {"results": [], "query": q}
    msg_store = request.app.state.chat_messages
    results = await msg_store.search(q, channel_id=channel_id, limit=limit)
    return {"results": results, "query": q}


@router.get("/api/chat/unread")
async def get_unread(request: Request):
    ch_store = request.app.state.chat_channels
    counts = await ch_store.get_unread_counts("user")
    return {"unread": counts}


@router.post("/api/chat/channels/{channel_id}/mark-read")
async def mark_read(request: Request, channel_id: str):
    body = await request.json()
    ch_store = request.app.state.chat_channels
    await ch_store.update_read_position("user", channel_id, body.get("message_id", ""))
    return {"status": "marked"}


# ── Chat page ─────────────────────────────────────────────────────────────────

@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "chat.html", {"active_page": "chat"})


@router.get("/chat/{channel_id}", response_class=HTMLResponse)
async def chat_channel_page(request: Request, channel_id: str):
    templates = request.app.state.templates
    ch_store = request.app.state.chat_channels
    channel = await ch_store.get_channel(channel_id)
    return templates.TemplateResponse(request, "chat.html", {
        "active_page": "chat",
        "channel": channel,
        "channel_id": channel_id,
    })
