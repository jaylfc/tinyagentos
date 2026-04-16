from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

AGENT_RUNTIME_PORT = 8100
AGENT_RUNTIME_TIMEOUT = 120.0


class AgentChatRouter:
    """Bridges user-authored chat messages into per-agent in-container
    HTTP runtimes (openclaw, smolagents adapters, etc.)."""

    def __init__(self, app_state: Any, *, http_client: httpx.AsyncClient | None = None):
        self._state = app_state
        self._client = http_client

    async def close(self) -> None:
        # The router owns no long-lived state; the http_client is provided
        # by the app lifespan and cleaned up there.
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

        members: list[str] = list(channel.get("members") or [])
        # Everyone except the user; for group DMs this may be multiple
        # agents, and each gets a chance to respond.
        agent_members = [m for m in members if m and m != "user"]
        if not agent_members:
            return

        config = self._state.config
        chat_messages = self._state.chat_messages
        chat_channels = self._state.chat_channels
        hub = self._state.chat_hub

        for agent_name in agent_members:
            agent = find_agent(config, agent_name)
            if agent is None:
                continue
            host = (agent.get("host") or "").strip()
            status = agent.get("status", "")
            if not host or status != "running":
                await self._post_system_reply(
                    agent_name, channel["id"],
                    f"[router] agent '{agent_name}' is not running (status={status or 'unknown'}).",
                    chat_messages, chat_channels, hub,
                )
                continue

            url = f"http://{host}:{AGENT_RUNTIME_PORT}/message"
            body = {
                "text": message.get("content", ""),
                "from": message.get("author_id", "user"),
                "thread_id": message.get("id"),
            }

            reply_text = ""
            try:
                client = self._client or httpx.AsyncClient(timeout=AGENT_RUNTIME_TIMEOUT)
                owns_client = self._client is None
                try:
                    resp = await client.post(url, json=body, timeout=AGENT_RUNTIME_TIMEOUT)
                    if resp.status_code == 200:
                        data = resp.json()
                        reply_text = (data.get("content") or "").strip()
                    else:
                        reply_text = f"[router] {agent_name} returned HTTP {resp.status_code}"
                finally:
                    if owns_client:
                        await client.aclose()
            except httpx.ConnectError:
                reply_text = f"[router] {agent_name} is unreachable at {host}:{AGENT_RUNTIME_PORT}"
            except httpx.TimeoutException:
                reply_text = f"[router] {agent_name} timed out after {AGENT_RUNTIME_TIMEOUT}s"
            except Exception as exc:  # noqa: BLE001
                reply_text = f"[router] {agent_name} errored: {exc}"

            if not reply_text:
                reply_text = f"[router] {agent_name} returned no content"

            await self._post_agent_reply(
                agent_name, channel["id"], reply_text, message.get("id"),
                chat_messages, chat_channels, hub,
            )

    async def _post_agent_reply(
        self, agent_name: str, channel_id: str, content: str,
        thread_id: str | None,
        chat_messages, chat_channels, hub,
    ) -> None:
        persisted = await chat_messages.send_message(
            channel_id=channel_id,
            author_id=agent_name,
            author_type="agent",
            content=content,
            content_type="text",
            state="complete",
            metadata={"thread_id": thread_id} if thread_id else None,
        )
        await chat_channels.update_last_message_at(channel_id)
        await hub.broadcast(channel_id, {"type": "message", "seq": hub.next_seq(), **persisted})

    async def _post_system_reply(
        self, agent_name: str, channel_id: str, content: str,
        chat_messages, chat_channels, hub,
    ) -> None:
        await self._post_agent_reply(agent_name, channel_id, content, None,
                                     chat_messages, chat_channels, hub)
