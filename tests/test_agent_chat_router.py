import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

from tinyagentos.agent_chat_router import AgentChatRouter


class _FakeBridge:
    """Duck-type BridgeSessionRegistry with call tracking."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def enqueue_user_message(self, slug: str, msg: dict) -> None:
        self.calls.append((slug, msg))


def _state_for(agent_record: dict | None, *, bridge: _FakeBridge | None = None):
    state = MagicMock()
    state.config = MagicMock()
    state.config.agents = [agent_record] if agent_record else []
    state.chat_messages = MagicMock()
    state.chat_messages.send_message = AsyncMock(return_value={
        "id": "m1", "channel_id": "c1",
        "author_id": "openclaw", "author_type": "agent",
        "content": "", "created_at": 1.0,
    })
    state.chat_channels = MagicMock()
    state.chat_channels.update_last_message_at = AsyncMock()
    state.chat_hub = MagicMock()
    state.chat_hub.broadcast = AsyncMock()
    state.chat_hub.next_seq = MagicMock(return_value=1)
    # bridge_sessions is set as an attribute; absence simulates misconfigured host
    if bridge is not None:
        state.bridge_sessions = bridge
    else:
        # Simulate missing attribute (not just None)
        del state.bridge_sessions
    return state


class TestAgentChatRouter:
    @pytest.mark.asyncio
    async def test_enqueues_to_bridge_when_agent_running(self):
        bridge = _FakeBridge()
        agent = {"name": "openclaw", "status": "running"}
        state = _state_for(agent, bridge=bridge)

        router = AgentChatRouter(state)
        message = {
            "id": "m1", "channel_id": "c1", "author_id": "user",
            "author_type": "user", "content": "hello",
            "created_at": 1.0,
        }
        channel = {"id": "c1", "members": ["user", "openclaw"]}
        await router._route(message, channel)

        assert len(bridge.calls) == 1
        slug, enqueued = bridge.calls[0]
        assert slug == "openclaw"
        assert enqueued["text"] == "hello"
        assert enqueued["from"] == "user"
        assert enqueued["trace_id"] == "m1"
        assert enqueued["channel_id"] == "c1"
        # System-reply path must NOT have been triggered.
        state.chat_messages.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_non_user_messages(self):
        bridge = _FakeBridge()
        state = _state_for({"name": "openclaw", "status": "running"}, bridge=bridge)
        router = AgentChatRouter(state)
        message = {"author_type": "agent", "content": "self-talk"}
        router.dispatch(message, {"id": "c1", "members": ["user", "openclaw"]})
        await asyncio.sleep(0.01)
        assert bridge.calls == []
        state.chat_messages.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_agent_record_is_noop(self):
        bridge = _FakeBridge()
        state = _state_for(None, bridge=bridge)
        router = AgentChatRouter(state)
        message = {
            "id": "m1", "channel_id": "c1", "author_id": "user",
            "author_type": "user", "content": "hi",
        }
        channel = {"id": "c1", "members": ["user", "ghost"]}
        await router._route(message, channel)
        assert bridge.calls == []
        state.chat_messages.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_running_agent_posts_system_reply(self):
        bridge = _FakeBridge()
        agent = {"name": "openclaw", "status": "deploying"}
        state = _state_for(agent, bridge=bridge)
        router = AgentChatRouter(state)
        message = {
            "id": "m1", "channel_id": "c1", "author_id": "user",
            "author_type": "user", "content": "hi",
        }
        channel = {"id": "c1", "members": ["user", "openclaw"]}
        await router._route(message, channel)

        assert bridge.calls == []
        state.chat_messages.send_message.assert_awaited_once()
        call = state.chat_messages.send_message.call_args.kwargs
        assert "not running" in call["content"]

    @pytest.mark.asyncio
    async def test_missing_bridge_registry_posts_system_reply(self):
        # bridge=None means bridge_sessions attribute is absent on state
        agent = {"name": "openclaw", "status": "running"}
        state = _state_for(agent, bridge=None)
        router = AgentChatRouter(state)
        message = {
            "id": "m1", "channel_id": "c1", "author_id": "user",
            "author_type": "user", "content": "hi",
        }
        channel = {"id": "c1", "members": ["user", "openclaw"]}
        await router._route(message, channel)

        state.chat_messages.send_message.assert_awaited_once()
        call = state.chat_messages.send_message.call_args.kwargs
        assert "bridge registry" in call["content"]
