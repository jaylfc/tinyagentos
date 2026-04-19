from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from tinyagentos.chat.reactions import maybe_trigger_semantic

router = APIRouter()
logger = logging.getLogger(__name__)


async def _capture_user_memory(
    user_memory,
    *,
    content: str,
    title: str,
    collection: str,
    metadata: dict,
    setting_key: str,
    user_id: str = "user",
) -> None:
    """Fire-and-forget user memory capture. Never raises."""
    if not user_memory or not content:
        return
    try:
        settings = await user_memory.get_settings(user_id)
        if not settings.get(setting_key):
            return
        await user_memory.save_chunk(
            user_id,
            content=content,
            title=title,
            collection=collection,
            metadata=metadata,
        )
    except Exception as e:  # pragma: no cover - capture is best-effort
        logger.debug(f"user memory capture failed: {e}")


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

                router_svc = getattr(websocket.app.state, "agent_chat_router", None)
                if router_svc is not None:
                    channel = await ch_store.get_channel(data["channel_id"])
                    if channel is not None:
                        router_svc.dispatch(message, channel)

                # Capture user message into user memory (async, non-blocking)
                user_memory = getattr(websocket.app.state, "user_memory", None)
                if user_memory:
                    asyncio.create_task(_capture_user_memory(
                        user_memory,
                        content=data.get("content", ""),
                        title=f"Message in {data['channel_id']}",
                        collection="conversations",
                        metadata={
                            "channel_id": data["channel_id"],
                            "message_id": message.get("id"),
                            "timestamp": message.get("created_at"),
                        },
                        setting_key="capture_conversations",
                        user_id=user_id,
                    ))

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

    channel_id = body["channel_id"]
    content = body.get("content") or ""

    # Guardrail: in a non-DM channel, a / message must address at least one
    # agent explicitly (@<slug> or @all). Otherwise a framework slash command
    # would broadcast to every agent in the channel, producing N different
    # /help outputs and (in some frameworks) triggering destructive side effects
    # like /clear on unaddressed agents.
    stripped = content.lstrip()
    if stripped.startswith("/"):
        channel = await ch_store.get_channel(channel_id)
        if channel and channel.get("type") != "dm":
            from tinyagentos.chat.mentions import parse_mentions
            members = list(channel.get("members") or [])
            mentions = parse_mentions(content, members)
            if not mentions.explicit and not mentions.all:
                return JSONResponse(
                    {"error": "slash commands in group channels must address an agent: use @<agent> /<cmd> or @all /<cmd>"},
                    status_code=400,
                )

    message = await msg_store.send_message(
        channel_id=channel_id,
        author_id=body["author_id"],
        author_type=body.get("author_type", "agent"),
        content=content,
        content_type=body.get("content_type", "text"),
        thread_id=body.get("thread_id"),
        embeds=body.get("embeds"),
        components=body.get("components"),
        attachments=body.get("attachments"),
        content_blocks=body.get("content_blocks"),
        metadata=body.get("metadata"),
        state=body.get("state", "complete"),
    )
    await ch_store.update_last_message_at(channel_id)
    await hub.broadcast(channel_id, {"type": "message", "seq": hub.next_seq(), **message})

    # Capture user messages into user memory (skip agent messages)
    if body.get("author_type", "agent") == "user":
        user_memory = getattr(request.app.state, "user_memory", None)
        if user_memory:
            asyncio.create_task(_capture_user_memory(
                user_memory,
                content=content,
                title=f"Message in {channel_id}",
                collection="conversations",
                metadata={
                    "channel_id": channel_id,
                    "message_id": message.get("id"),
                    "timestamp": message.get("created_at"),
                },
                setting_key="capture_conversations",
            ))

    # Auto-archive every message for the zero-loss layer
    archive = getattr(request.app.state, "archive", None)
    if archive:
        try:
            await archive.record(
                "conversation",
                {
                    "content": content,
                    "channel_id": channel_id,
                    "message_id": message.get("id"),
                    "author_id": body["author_id"],
                    "author_type": body.get("author_type", "agent"),
                },
                agent_name=body["author_id"] if body.get("author_type") == "agent" else None,
                summary=content[:100],
            )
        except Exception:
            pass  # Never block chat for archive failures

    router_svc = getattr(request.app.state, "agent_chat_router", None)
    if router_svc is not None:
        channel = await ch_store.get_channel(channel_id)
        if channel is not None:
            router_svc.dispatch(message, channel)

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
async def list_channels(
    request: Request,
    member: str | None = None,
    archived: bool | None = None,
):
    ch_store = request.app.state.chat_channels
    channels = await ch_store.list_channels(member_id=member, archived=archived)
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


@router.delete("/api/chat/channels/{channel_id}/members/{member_id}")
async def remove_channel_member(request: Request, channel_id: str, member_id: str):
    ch_store = request.app.state.chat_channels
    await ch_store.remove_member(channel_id, member_id)
    return {"status": "removed"}


# ── Admin endpoints (UI-driven channel control-plane) ─────────────────────────

@router.patch("/api/chat/channels/{channel_id}")
async def update_channel_settings(channel_id: str, body: dict, request: Request):
    """Update channel settings. Body may include: response_mode, max_hops,
    cooldown_seconds, topic, name. Each is optional; only provided keys are
    applied. Returns 400 on validation failure."""
    state = request.app.state
    chs = state.chat_channels
    ch = await chs.get_channel(channel_id)
    if ch is None:
        return JSONResponse({"error": "channel not found"}, status_code=404)
    try:
        if "response_mode" in body:
            await chs.set_response_mode(channel_id, body["response_mode"])
        if "max_hops" in body:
            await chs.set_max_hops(channel_id, int(body["max_hops"]))
        if "cooldown_seconds" in body:
            await chs.set_cooldown_seconds(channel_id, int(body["cooldown_seconds"]))
        if "topic" in body:
            topic = str(body["topic"])
            if len(topic) > 500:
                return JSONResponse({"error": "topic must be <= 500 chars"}, status_code=400)
            await chs.update_channel(channel_id, topic=topic)
        if "name" in body:
            name = str(body["name"]).strip()
            if not name or len(name) > 100:
                return JSONResponse({"error": "name must be 1..100 chars"}, status_code=400)
            await chs.update_channel(channel_id, name=name)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"ok": True}, status_code=200)


@router.post("/api/chat/channels/{channel_id}/members")
async def modify_channel_members(channel_id: str, body: dict, request: Request):
    """Add or remove a member. Body: {"action": "add" | "remove", "slug": "..."}."""
    action = (body.get("action") or "").lower()
    slug = (body.get("slug") or "").lstrip("@")
    if action not in ("add", "remove") or not slug:
        return JSONResponse({"error": "action must be add|remove, slug required"}, status_code=400)
    state = request.app.state
    chs = state.chat_channels
    ch = await chs.get_channel(channel_id)
    if ch is None:
        return JSONResponse({"error": "channel not found"}, status_code=404)
    if action == "add":
        known = {a.get("name") for a in getattr(state.config, "agents", []) or []}
        if slug != "user" and slug not in known:
            return JSONResponse({"error": f"unknown agent: {slug}"}, status_code=400)
        await chs.add_member(channel_id, slug)
    else:
        await chs.remove_member(channel_id, slug)
    return JSONResponse({"ok": True}, status_code=200)


@router.post("/api/chat/channels/{channel_id}/muted")
async def modify_channel_muted(channel_id: str, body: dict, request: Request):
    """Add or remove an agent from the channel's muted list.
    Body: {"action": "add" | "remove", "slug": "..."}."""
    action = (body.get("action") or "").lower()
    slug = (body.get("slug") or "").lstrip("@")
    if action not in ("add", "remove") or not slug:
        return JSONResponse({"error": "action must be add|remove, slug required"}, status_code=400)
    state = request.app.state
    chs = state.chat_channels
    ch = await chs.get_channel(channel_id)
    if ch is None:
        return JSONResponse({"error": "channel not found"}, status_code=404)
    if action == "add":
        await chs.mute_agent(channel_id, slug)
    else:
        await chs.unmute_agent(channel_id, slug)
    return JSONResponse({"ok": True}, status_code=200)


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


# ── Reactions ────────────────────────────────────────────────────────────────

@router.post("/api/chat/messages/{message_id}/reactions")
async def add_reaction(message_id: str, body: dict, request: Request):
    emoji = body.get("emoji")
    author_id = body.get("author_id")
    author_type = body.get("author_type", "user")
    if not emoji or not author_id:
        return JSONResponse({"error": "emoji and author_id required"}, status_code=400)
    state = request.app.state
    msg = await state.chat_messages.get_message(message_id)
    if msg is None:
        return JSONResponse({"error": "message not found"}, status_code=404)
    await state.chat_messages.add_reaction(message_id, emoji, author_id)
    channel = await state.chat_channels.get_channel(msg["channel_id"])
    await state.chat_hub.broadcast(msg["channel_id"], {
        "type": "reaction_added",
        "message_id": message_id,
        "emoji": emoji,
        "author_id": author_id,
    })
    if channel is not None:
        await maybe_trigger_semantic(
            emoji=emoji, message=msg,
            reactor_id=author_id, reactor_type=author_type,
            channel=channel, state=state,
        )
    return JSONResponse({"ok": True}, status_code=200)


@router.delete("/api/chat/messages/{message_id}/reactions/{emoji}")
async def remove_reaction(message_id: str, emoji: str, author_id: str, request: Request):
    state = request.app.state
    await state.chat_messages.remove_reaction(message_id, emoji, author_id)
    msg = await state.chat_messages.get_message(message_id)
    if msg:
        await state.chat_hub.broadcast(msg["channel_id"], {
            "type": "reaction_removed",
            "message_id": message_id,
            "emoji": emoji,
            "author_id": author_id,
        })
    return JSONResponse({"ok": True}, status_code=200)


@router.get("/api/chat/channels/{channel_id}/wants_reply")
async def list_wants_reply(channel_id: str, request: Request):
    reg = getattr(request.app.state, "wants_reply", None)
    if reg is None:
        return JSONResponse({"slugs": []})
    return JSONResponse({"slugs": reg.list(channel_id)})


# ── Canvas ───────────────────────────────────────────────────────────────────

@router.post("/api/canvas/generate")
async def create_canvas(request: Request):
    """Create a new canvas page."""
    body = await request.json()
    canvas_store = request.app.state.canvas_store
    canvas = await canvas_store.create(
        title=body.get("title", "Untitled"),
        content=body.get("content", ""),
        style=body.get("style", "auto"),
        format=body.get("format", "markdown"),
        created_by=body.get("agent_name", "system"),
    )
    return {
        "canvas_id": canvas["id"],
        "canvas_url": f"/canvas/{canvas['id']}",
        "edit_token": canvas["edit_token"],
    }


@router.post("/api/canvas/{canvas_id}/update")
async def update_canvas(request: Request, canvas_id: str):
    """Update canvas content (requires edit_token)."""
    body = await request.json()
    canvas_store = request.app.state.canvas_store
    updated = await canvas_store.update(
        canvas_id,
        edit_token=body.get("edit_token", ""),
        content=body.get("content"),
        title=body.get("title"),
    )
    if not updated:
        return JSONResponse({"error": "Invalid edit token or canvas not found"}, status_code=403)
    # Broadcast to canvas viewers
    hub = request.app.state.chat_hub
    canvas = await canvas_store.get(canvas_id)
    await hub.broadcast(f"canvas:{canvas_id}", {"type": "canvas_update", "content": canvas["content"], "title": canvas["title"]})
    return {"status": "updated"}


@router.get("/api/canvas/{canvas_id}/data")
async def canvas_data(request: Request, canvas_id: str):
    """Get canvas data as JSON."""
    canvas_store = request.app.state.canvas_store
    canvas = await canvas_store.get(canvas_id)
    if not canvas:
        return JSONResponse({"error": "Canvas not found"}, status_code=404)
    return canvas


@router.delete("/api/canvas/{canvas_id}")
async def delete_canvas(request: Request, canvas_id: str):
    canvas_store = request.app.state.canvas_store
    deleted = await canvas_store.delete(canvas_id)
    if not deleted:
        return JSONResponse({"error": "Canvas not found"}, status_code=404)
    return {"status": "deleted"}


@router.get("/api/canvas")
async def list_canvases(request: Request, limit: int = 50):
    canvas_store = request.app.state.canvas_store
    canvases = await canvas_store.list_all(limit=limit)
    return {"canvases": canvases}


@router.websocket("/ws/canvas/{canvas_id}")
async def canvas_ws(websocket: WebSocket, canvas_id: str):
    """WebSocket for live canvas updates."""
    await websocket.accept()
    hub = websocket.app.state.chat_hub
    canvas_channel = f"canvas:{canvas_id}"
    hub.join(websocket, canvas_channel)
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        pass
    finally:
        hub.leave(websocket, canvas_channel)


