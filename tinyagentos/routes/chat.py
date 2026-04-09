from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

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
