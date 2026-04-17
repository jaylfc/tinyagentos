"""BridgeSessionRegistry — per-agent queue + accumulator for the openclaw bridge.

One queue per agent slug holds events that taOS needs to deliver to openclaw
(user_message, abort). openclaw subscribes once at startup via SSE and drains
the queue; replies from openclaw flow back through POST /reply and are written
to the trace store + broadcast via the chat hub.

Single-subscriber semantics: if openclaw reconnects, the old stream's generator
sees a sentinel and exits; the new connection replaces it.

Delta buffering: per (slug, trace_id) a StringIO-like accumulator collects
``delta`` payloads. On ``final`` the buffer is flushed into the trace record
and the final chat message is created/completed. This keeps the trace store
clean (one message_out per turn, not one per token).

Queue size: unbounded in MVP (user messages are low-rate and tiny). Mark as
future bounded-queue work if needed.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

# Sentinel pushed to a subscriber queue to tell its generator to exit.
_DISCONNECT = object()

TICK_INTERVAL = 15  # seconds between keepalive ticks


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


class _AgentSession:
    """Per-agent mutable state held by the registry."""

    def __init__(self) -> None:
        # Queue of SSE payloads (dicts) to push to the openclaw subscriber.
        self.queue: asyncio.Queue[Any] = asyncio.Queue()
        # Maps trace_id -> StringIO accumulator for delta buffering.
        self._delta_buffers: dict[str, io.StringIO] = {}
        # Maps trace_id -> pending chat message id (created as 'streaming').
        self._pending_msg_ids: dict[str, str] = {}

    def accumulate_delta(self, trace_id: str, content: str) -> None:
        if trace_id not in self._delta_buffers:
            self._delta_buffers[trace_id] = io.StringIO()
        self._delta_buffers[trace_id].write(content)

    def flush_delta(self, trace_id: str) -> str:
        buf = self._delta_buffers.pop(trace_id, None)
        if buf is None:
            return ""
        return buf.getvalue()

    def set_pending_msg(self, trace_id: str, msg_id: str) -> None:
        self._pending_msg_ids[trace_id] = msg_id

    def pop_pending_msg(self, trace_id: str) -> str | None:
        return self._pending_msg_ids.pop(trace_id, None)


class BridgeSessionRegistry:
    """Holds one _AgentSession per slug. Thread-safe via asyncio.

    Dependencies passed at construction:
        trace_registry  — TraceStoreRegistry (app.state.trace_registry)
        chat_messages   — ChatMessageStore   (app.state.chat_messages)
        chat_channels   — ChatChannelStore   (app.state.chat_channels)
        chat_hub        — ChatHub            (app.state.chat_hub)

    All four are optional so unit tests can inject fakes or None.
    """

    def __init__(
        self,
        trace_registry=None,
        chat_messages=None,
        chat_channels=None,
        chat_hub=None,
    ) -> None:
        self._trace_registry = trace_registry
        self._chat_messages = chat_messages
        self._chat_channels = chat_channels
        self._chat_hub = chat_hub
        self._sessions: dict[str, _AgentSession] = {}
        self._lock = asyncio.Lock()

    def _get_or_create(self, slug: str) -> _AgentSession:
        if slug not in self._sessions:
            self._sessions[slug] = _AgentSession()
        return self._sessions[slug]

    async def enqueue_user_message(self, slug: str, msg: dict) -> None:
        """Push a user_message event onto the agent's SSE queue.

        Called by the chat router when a message is dispatched to the
        openclaw-backed agent.
        """
        async with self._lock:
            session = self._get_or_create(slug)
        await session.queue.put({
            "event": "user_message",
            "data": msg,
        })

    async def subscribe(self, slug: str) -> AsyncIterator[str]:
        """Async generator yielding raw SSE text frames.

        Manages single-subscriber semantics: on entry, pushes _DISCONNECT
        into any existing queue so a stale generator exits promptly, then
        drains any pending items into the new queue so no user_messages
        already enqueued are lost. A background keepalive task fires tick
        events every TICK_INTERVAL seconds.
        """
        async with self._lock:
            session = self._get_or_create(slug)
            old_queue = session.queue
            new_queue: asyncio.Queue = asyncio.Queue()
            # Drain pending items (e.g. user messages enqueued before subscribe)
            # into the new queue before signalling the old subscriber.
            pending = []
            while not old_queue.empty():
                try:
                    item = old_queue.get_nowait()
                    if item is not _DISCONNECT:
                        pending.append(item)
                except asyncio.QueueEmpty:
                    break
            # Signal any existing subscriber to exit via its queue position.
            old_queue.put_nowait(_DISCONNECT)
            # Seed the new queue with any saved pending items.
            for item in pending:
                new_queue.put_nowait(item)
            session.queue = new_queue
            queue = new_queue

        tick_task: asyncio.Task | None = None

        async def _tick() -> None:
            while True:
                await asyncio.sleep(TICK_INTERVAL)
                await queue.put({"event": "tick", "data": {"ts": time.time()}})

        try:
            tick_task = asyncio.create_task(_tick())
            while True:
                item = await queue.get()
                if item is _DISCONNECT:
                    break
                event_type = item.get("event", "message")
                data = json.dumps(item.get("data", {}))
                yield f"event: {event_type}\ndata: {data}\n\n"
        finally:
            if tick_task is not None:
                tick_task.cancel()

    async def record_reply(self, slug: str, body: dict) -> None:
        """Process a reply POST from openclaw.

        Writes trace events, accumulates deltas, creates/updates chat messages,
        and broadcasts via the hub. All failures are caught and logged — never
        re-raises so the route always returns 202.
        """
        try:
            await self._handle_reply(slug, body)
        except Exception:
            logger.exception("bridge_session: record_reply error for agent %s", slug)

    async def _handle_reply(self, slug: str, body: dict) -> None:
        kind = body.get("kind", "")
        trace_id = body.get("trace_id") or _new_id()
        msg_id = body.get("id") or _new_id()
        content = body.get("content") or ""

        async with self._lock:
            session = self._get_or_create(slug)

        if kind == "delta":
            session.accumulate_delta(trace_id, content)
            # Ensure a streaming placeholder chat message exists.
            pending_msg_id = session._pending_msg_ids.get(trace_id)
            if pending_msg_id is None and self._chat_messages and self._chat_channels:
                channel_id = await self._resolve_channel(slug)
                if channel_id:
                    new_msg = await self._chat_messages.send_message(
                        channel_id=channel_id,
                        author_id=slug,
                        author_type="agent",
                        content="",
                        state="streaming",
                        metadata={"trace_id": trace_id, "openclaw_msg_id": msg_id},
                    )
                    session.set_pending_msg(trace_id, new_msg["id"])
                    if self._chat_channels:
                        await self._chat_channels.update_last_message_at(channel_id)
                    if self._chat_hub:
                        await self._chat_hub.broadcast(channel_id, {
                            "type": "message",
                            "seq": self._chat_hub.next_seq(),
                            **new_msg,
                        })
                    pending_msg_id = new_msg["id"]
            # Broadcast delta.
            if pending_msg_id and self._chat_hub:
                channel_id = await self._resolve_channel(slug)
                if channel_id:
                    await self._chat_hub.broadcast(channel_id, {
                        "type": "message_delta",
                        "seq": self._chat_hub.next_seq(),
                        "message_id": pending_msg_id,
                        "channel_id": channel_id,
                        "delta": content,
                    })

        elif kind == "final":
            accumulated = session.flush_delta(trace_id)
            final_content = content or accumulated
            pending_msg_id = session.pop_pending_msg(trace_id)
            channel_id = await self._resolve_channel(slug)

            # Write trace event.
            if self._trace_registry:
                store = await self._trace_registry.get(slug)
                await store.record(
                    "message_out",
                    trace_id=trace_id,
                    channel_id=channel_id,
                    payload={"content": final_content},
                )

            if channel_id:
                if pending_msg_id and self._chat_messages:
                    # Edit the streaming placeholder to final content.
                    await self._chat_messages.edit_message(pending_msg_id, final_content)
                    await self._chat_messages.update_state(pending_msg_id, "complete")
                    if self._chat_hub:
                        await self._chat_hub.broadcast(channel_id, {
                            "type": "message_edit",
                            "seq": self._chat_hub.next_seq(),
                            "message_id": pending_msg_id,
                            "content": final_content,
                            "edited_at": time.time(),
                        })
                        await self._chat_hub.broadcast(channel_id, {
                            "type": "message_state",
                            "seq": self._chat_hub.next_seq(),
                            "message_id": pending_msg_id,
                            "state": "complete",
                        })
                elif self._chat_messages and self._chat_channels:
                    # No streaming placeholder — create the message directly.
                    new_msg = await self._chat_messages.send_message(
                        channel_id=channel_id,
                        author_id=slug,
                        author_type="agent",
                        content=final_content,
                        state="complete",
                        metadata={"trace_id": trace_id, "openclaw_msg_id": msg_id},
                    )
                    await self._chat_channels.update_last_message_at(channel_id)
                    if self._chat_hub:
                        await self._chat_hub.broadcast(channel_id, {
                            "type": "message",
                            "seq": self._chat_hub.next_seq(),
                            **new_msg,
                        })

        elif kind == "tool_call":
            channel_id = await self._resolve_channel(slug)
            if self._trace_registry:
                store = await self._trace_registry.get(slug)
                await store.record(
                    "tool_call",
                    trace_id=trace_id,
                    channel_id=channel_id,
                    payload={
                        "tool": body.get("tool") or "",
                        "args": body.get("args") or {},
                        "caller": "openclaw",
                    },
                )

        elif kind == "tool_result":
            channel_id = await self._resolve_channel(slug)
            if self._trace_registry:
                store = await self._trace_registry.get(slug)
                await store.record(
                    "tool_result",
                    trace_id=trace_id,
                    channel_id=channel_id,
                    payload={
                        "tool": body.get("tool") or "",
                        "result": body.get("result"),
                        "success": body.get("success", True),
                    },
                )

        elif kind == "error":
            error_text = body.get("error") or ""
            channel_id = await self._resolve_channel(slug)
            if self._trace_registry:
                store = await self._trace_registry.get(slug)
                await store.record(
                    "error",
                    trace_id=trace_id,
                    channel_id=channel_id,
                    payload={"stage": "openclaw", "message": error_text},
                )
            # Set any pending message to error state.
            pending_msg_id = session.pop_pending_msg(trace_id)
            if pending_msg_id and self._chat_messages:
                await self._chat_messages.update_state(pending_msg_id, "error")
                if channel_id and self._chat_hub:
                    await self._chat_hub.broadcast(channel_id, {
                        "type": "message_state",
                        "seq": self._chat_hub.next_seq(),
                        "message_id": pending_msg_id,
                        "state": "error",
                    })

        elif kind == "reasoning":
            channel_id = await self._resolve_channel(slug)
            if self._trace_registry:
                store = await self._trace_registry.get(slug)
                await store.record(
                    "reasoning",
                    trace_id=trace_id,
                    channel_id=channel_id,
                    payload={"text": content},
                )
        # "delta" without a matching kind is silently ignored.

    async def _resolve_channel(self, slug: str) -> str | None:
        """Return the DM channel id for the agent, or None if unavailable."""
        if not self._chat_channels:
            return None
        try:
            channels = await self._chat_channels.list_channels(member_id=slug)
            for ch in channels:
                if ch.get("type") == "dm":
                    return ch["id"]
            # Fall back: return first channel the agent is a member of.
            if channels:
                return channels[0]["id"]
        except Exception:
            logger.debug("bridge_session: channel lookup failed for %s", slug)
        return None
