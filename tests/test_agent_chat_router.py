import asyncio
import json

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock

from tinyagentos.agent_chat_router import AgentChatRouter


def _state_for(agent_record: dict | None, *, channels_return: dict | None = None):
    state = MagicMock()
    state.config = MagicMock()
    state.config.agents = [agent_record] if agent_record else []
    state.chat_messages = MagicMock()
    state.chat_messages.send_message = AsyncMock(return_value={"id": "m1", "channel_id": "c1",
                                                                "author_id": "openclaw",
                                                                "author_type": "agent",
                                                                "content": "",
                                                                "created_at": 1.0})
    state.chat_channels = MagicMock()
    state.chat_channels.update_last_message_at = AsyncMock()
    state.chat_hub = MagicMock()
    state.chat_hub.broadcast = AsyncMock()
    state.chat_hub.next_seq = MagicMock(return_value=1)
    return state


class TestAgentChatRouter:
    @pytest.mark.asyncio
    async def test_routes_user_message_to_agent_runtime(self):
        agent = {"name": "openclaw", "host": "10.0.0.42", "status": "running"}
        state = _state_for(agent)

        def handler(request):
            data = json.loads(request.content)
            assert data["text"] == "hi"
            assert data["from"] == "user"
            return httpx.Response(200, json={"content": "hello back"})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            router = AgentChatRouter(state, http_client=client)
            message = {"id": "m1", "channel_id": "c1", "author_id": "user",
                       "author_type": "user", "content": "hi"}
            channel = {"id": "c1", "members": ["user", "openclaw"]}
            await router._route(message, channel)

        state.chat_messages.send_message.assert_awaited_once()
        call = state.chat_messages.send_message.call_args.kwargs
        assert call["author_id"] == "openclaw"
        assert call["author_type"] == "agent"
        assert call["content"] == "hello back"
        state.chat_hub.broadcast.assert_awaited()

    @pytest.mark.asyncio
    async def test_skips_non_user_messages(self):
        state = _state_for({"name": "openclaw", "host": "10.0.0.42", "status": "running"})
        router = AgentChatRouter(state)
        message = {"author_type": "agent", "content": "self-talk"}
        router.dispatch(message, {"id": "c1", "members": ["user", "openclaw"]})
        await asyncio.sleep(0.01)
        state.chat_messages.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_agent_record_is_noop(self):
        state = _state_for(None)  # no agent in config
        router = AgentChatRouter(state)
        message = {"id": "m1", "channel_id": "c1", "author_id": "user",
                   "author_type": "user", "content": "hi"}
        channel = {"id": "c1", "members": ["user", "ghost"]}
        await router._route(message, channel)
        state.chat_messages.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_running_agent_posts_system_reply(self):
        agent = {"name": "openclaw", "host": "", "status": "deploying"}
        state = _state_for(agent)
        router = AgentChatRouter(state)
        message = {"id": "m1", "channel_id": "c1", "author_id": "user",
                   "author_type": "user", "content": "hi"}
        channel = {"id": "c1", "members": ["user", "openclaw"]}
        await router._route(message, channel)

        state.chat_messages.send_message.assert_awaited_once()
        call = state.chat_messages.send_message.call_args.kwargs
        assert "not running" in call["content"]

    @pytest.mark.asyncio
    async def test_connect_error_reports_unreachable(self):
        agent = {"name": "openclaw", "host": "10.0.0.42", "status": "running"}
        state = _state_for(agent)

        def handler(request):
            raise httpx.ConnectError("refused", request=request)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            router = AgentChatRouter(state, http_client=client)
            message = {"id": "m1", "channel_id": "c1", "author_id": "user",
                       "author_type": "user", "content": "hi"}
            channel = {"id": "c1", "members": ["user", "openclaw"]}
            await router._route(message, channel)

        call = state.chat_messages.send_message.call_args.kwargs
        assert "unreachable" in call["content"]
