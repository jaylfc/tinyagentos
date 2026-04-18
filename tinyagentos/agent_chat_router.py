from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentChatRouter:
    """Bridges user-authored chat messages into per-agent SSE queues via
    BridgeSessionRegistry. The openclaw fork patch subscribes to each agent's
    queue at container startup; replies flow back through
    POST /api/openclaw/sessions/{slug}/reply (routes/openclaw.py)."""

    def __init__(self, app_state: Any):
        self._state = app_state

    async def close(self) -> None:
        # Registry lifecycle belongs to app.state; nothing to tear down here.
        return

    def dispatch(self, message: dict, channel: dict) -> None:
        """Fire-and-forget entry point. Callers invoke this right after a
        message has been persisted and broadcast; we run the routing in a
        background task so the caller's latency is unchanged."""
        if message.get("author_type") != "user":
            return
        asyncio.create_task(self._route(message, channel))

    async def _route(self, message: dict, channel: dict) -> None:
        try:
            await self._route_inner(message, channel)
        except Exception as exc:  # noqa: BLE001
            logger.warning("agent chat router failed: %s", exc, exc_info=True)

    async def _route_inner(self, message: dict, channel: dict) -> None:
        from tinyagentos.agent_db import find_agent

        members = list(channel.get("members") or [])
        agent_members = [m for m in members if m and m != "user"]
        if not agent_members:
            return

        config = self._state.config
        bridge = getattr(self._state, "bridge_sessions", None)

        for agent_name in agent_members:
            agent = find_agent(config, agent_name)
            if agent is None:
                continue
            status = agent.get("status", "")
            if status != "running":
                await self._post_system_reply(
                    agent_name, channel["id"],
                    f"[router] agent '{agent_name}' is not running (status={status or 'unknown'}).",
                )
                continue
            if bridge is None:
                await self._post_system_reply(
                    agent_name, channel["id"],
                    "[router] bridge registry not configured on this host.",
                )
                continue

            # The openclaw bridge patch is subscribed to this agent's SSE event
            # stream. Enqueue the user message; the bridge picks it up and runs
            # it through openclaw's session pipeline. Replies flow back via
            # POST /api/openclaw/sessions/{agent}/reply (handled in
            # routes/openclaw.py), which writes traces and broadcasts to the
            # chat hub -- no polling, no HTTP callback from this path.
            await bridge.enqueue_user_message(
                agent_name,
                {
                    "id": message.get("id"),
                    "trace_id": message.get("id"),  # MVP: message id IS the trace id
                    "channel_id": message.get("channel_id"),
                    "from": message.get("author_id", "user"),
                    "text": message.get("content", ""),
                    "created_at": message.get("created_at"),
                },
            )

    async def _post_system_reply(
        self, agent_name: str, channel_id: str, content: str,
    ) -> None:
        chat_messages = self._state.chat_messages
        chat_channels = self._state.chat_channels
        hub = self._state.chat_hub
        persisted = await chat_messages.send_message(
            channel_id=channel_id,
            author_id=agent_name,
            author_type="agent",
            content=content,
            content_type="text",
            state="complete",
            metadata=None,
        )
        await chat_channels.update_last_message_at(channel_id)
        await hub.broadcast(channel_id, {"type": "message", "seq": hub.next_seq(), **persisted})
