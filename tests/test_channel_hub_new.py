"""Tests for new Channel Hub connectors and framework adapters."""
from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tinyagentos.channel_hub.message import IncomingMessage, OutgoingMessage


# ---------------------------------------------------------------------------
# Discord Connector
# ---------------------------------------------------------------------------

class TestDiscordConnector:
    @pytest.mark.asyncio
    async def test_send_text_response(self):
        from tinyagentos.channel_hub.discord_connector import DiscordConnector

        router = MagicMock()
        connector = DiscordConnector(
            bot_token="fake_token", agent_name="test", router=router, channel_ids=["ch1"],
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock()

        response = OutgoingMessage(content="Hello from Discord!")
        await connector._send_response(mock_client, "ch1", response)

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/channels/ch1/messages" in call_args[0][0]
        assert call_args[1]["json"]["content"] == "Hello from Discord!"

    @pytest.mark.asyncio
    async def test_send_response_with_buttons(self):
        from tinyagentos.channel_hub.discord_connector import DiscordConnector

        router = MagicMock()
        connector = DiscordConnector(
            bot_token="fake_token", agent_name="test", router=router,
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock()

        response = OutgoingMessage(
            content="Pick one:",
            buttons=[{"label": "A", "action": "pick_a"}, {"label": "B", "action": "pick_b"}],
        )
        await connector._send_response(mock_client, "ch1", response)

        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert "components" in payload
        components = payload["components"][0]["components"]
        assert len(components) == 2
        assert components[0]["label"] == "A"
        assert components[0]["custom_id"] == "pick_a"

    @pytest.mark.asyncio
    async def test_send_response_with_images(self):
        from tinyagentos.channel_hub.discord_connector import DiscordConnector

        router = MagicMock()
        connector = DiscordConnector(
            bot_token="fake_token", agent_name="test", router=router,
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock()

        response = OutgoingMessage(
            content="Check this out",
            images=["http://example.com/img.png"],
        )
        await connector._send_response(mock_client, "ch1", response)

        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert "embeds" in payload
        assert payload["embeds"][0]["image"]["url"] == "http://example.com/img.png"

    @pytest.mark.asyncio
    async def test_send_passthrough(self):
        from tinyagentos.channel_hub.discord_connector import DiscordConnector

        router = MagicMock()
        connector = DiscordConnector(
            bot_token="fake_token", agent_name="test", router=router,
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock()

        response = OutgoingMessage(
            passthrough=True,
            passthrough_platform="discord",
            passthrough_payload={"content": "raw payload", "tts": True},
        )
        await connector._send_response(mock_client, "ch1", response)

        call_args = mock_client.post.call_args
        assert "/channels/ch1/messages" in call_args[0][0]
        assert call_args[1]["json"]["tts"] is True

    @pytest.mark.asyncio
    async def test_handle_message_routes(self):
        from tinyagentos.channel_hub.discord_connector import DiscordConnector

        mock_router = AsyncMock()
        mock_router.route_message = AsyncMock(return_value=None)
        connector = DiscordConnector(
            bot_token="fake", agent_name="bot1", router=mock_router, channel_ids=["ch1"],
        )

        mock_client = AsyncMock()
        msg = {
            "id": "msg123",
            "author": {"id": "user1", "username": "Jay"},
            "content": "hello discord",
        }
        await connector._handle_message(mock_client, "ch1", msg)

        mock_router.route_message.assert_called_once()
        incoming = mock_router.route_message.call_args[0][1]
        assert incoming.text == "hello discord"
        assert incoming.from_name == "Jay"
        assert incoming.platform == "discord"
        assert incoming.channel_id == "ch1"

    @pytest.mark.asyncio
    async def test_check_channel_skips_own_messages(self):
        from tinyagentos.channel_hub.discord_connector import DiscordConnector

        mock_router = AsyncMock()
        mock_router.route_message = AsyncMock(return_value=None)
        connector = DiscordConnector(
            bot_token="fake", agent_name="bot1", router=mock_router, channel_ids=["ch1"],
        )
        connector._bot_user_id = "bot_id_123"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": "m2", "author": {"id": "bot_id_123", "username": "Bot"}, "content": "I said this"},
            {"id": "m1", "author": {"id": "user1", "username": "Jay"}, "content": "hey"},
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        await connector._check_channel(mock_client, "ch1")

        # Only the user message should be routed, not the bot's own message
        assert mock_router.route_message.call_count == 1
        incoming = mock_router.route_message.call_args[0][1]
        assert incoming.text == "hey"

    @pytest.mark.asyncio
    async def test_check_channel_updates_last_id(self):
        from tinyagentos.channel_hub.discord_connector import DiscordConnector

        mock_router = AsyncMock()
        mock_router.route_message = AsyncMock(return_value=None)
        connector = DiscordConnector(
            bot_token="fake", agent_name="bot1", router=mock_router, channel_ids=["ch1"],
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": "m5", "author": {"id": "u1", "username": "A"}, "content": "newest"},
            {"id": "m4", "author": {"id": "u2", "username": "B"}, "content": "older"},
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        await connector._check_channel(mock_client, "ch1")
        assert connector._last_message_ids["ch1"] == "m5"

    @pytest.mark.asyncio
    async def test_check_channel_non_200(self):
        from tinyagentos.channel_hub.discord_connector import DiscordConnector

        mock_router = AsyncMock()
        mock_router.route_message = AsyncMock(return_value=None)
        connector = DiscordConnector(
            bot_token="fake", agent_name="bot1", router=mock_router, channel_ids=["ch1"],
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        await connector._check_channel(mock_client, "ch1")
        mock_router.route_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        from tinyagentos.channel_hub.discord_connector import DiscordConnector

        router = MagicMock()
        connector = DiscordConnector(
            bot_token="fake", agent_name="test", router=router, channel_ids=["ch1"],
        )

        with patch.object(connector, "_poll_loop", new_callable=AsyncMock):
            # Mock the start GET for bot user ID
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"id": "bot123"}

            with patch("tinyagentos.channel_hub.discord_connector.httpx.AsyncClient") as mock_httpx:
                mock_client_instance = AsyncMock()
                mock_client_instance.get = AsyncMock(return_value=mock_resp)
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=False)
                mock_httpx.return_value = mock_client_instance

                await connector.start()
                assert connector._running is True
                assert connector._bot_user_id == "bot123"

                await connector.stop()
                assert connector._running is False

    @pytest.mark.asyncio
    async def test_buttons_capped_at_five(self):
        from tinyagentos.channel_hub.discord_connector import DiscordConnector

        router = MagicMock()
        connector = DiscordConnector(
            bot_token="fake_token", agent_name="test", router=router,
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock()

        # 7 buttons — Discord max is 5 per row
        buttons = [{"label": f"B{i}", "action": f"a{i}"} for i in range(7)]
        response = OutgoingMessage(content="Pick:", buttons=buttons)
        await connector._send_response(mock_client, "ch1", response)

        call_args = mock_client.post.call_args
        components = call_args[1]["json"]["components"][0]["components"]
        assert len(components) == 5

    @pytest.mark.asyncio
    async def test_empty_response_not_sent(self):
        from tinyagentos.channel_hub.discord_connector import DiscordConnector

        router = MagicMock()
        connector = DiscordConnector(
            bot_token="fake_token", agent_name="test", router=router,
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock()

        response = OutgoingMessage()  # empty
        await connector._send_response(mock_client, "ch1", response)

        mock_client.post.assert_not_called()


# ---------------------------------------------------------------------------
# WebChat Connector
# ---------------------------------------------------------------------------

class TestWebChatConnector:
    @pytest.mark.asyncio
    async def test_handle_websocket_message(self):
        from tinyagentos.channel_hub.webchat_connector import WebChatConnector

        mock_router = AsyncMock()
        response = OutgoingMessage(content="Hello back!")
        mock_router.route_message = AsyncMock(return_value=response)

        connector = WebChatConnector(agent_name="test-agent", router=mock_router)

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive_text = AsyncMock(
            side_effect=[
                json.dumps({"name": "Jay", "text": "hello"}),
                Exception("disconnect"),  # simulate end
            ]
        )
        mock_ws.send_text = AsyncMock()

        await connector.handle_websocket(mock_ws)

        mock_ws.accept.assert_called_once()
        mock_router.route_message.assert_called_once()
        incoming = mock_router.route_message.call_args[0][1]
        assert incoming.text == "hello"
        assert incoming.from_name == "Jay"
        assert incoming.platform == "web"

        mock_ws.send_text.assert_called_once()
        sent_data = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent_data["content"] == "Hello back!"

    @pytest.mark.asyncio
    async def test_handle_websocket_no_response(self):
        from tinyagentos.channel_hub.webchat_connector import WebChatConnector

        mock_router = AsyncMock()
        mock_router.route_message = AsyncMock(return_value=None)

        connector = WebChatConnector(agent_name="test-agent", router=mock_router)

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive_text = AsyncMock(
            side_effect=[
                json.dumps({"text": "hello"}),
                Exception("done"),
            ]
        )
        mock_ws.send_text = AsyncMock()

        await connector.handle_websocket(mock_ws)

        # No response sent when route returns None
        mock_ws.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_connection_cleanup(self):
        from tinyagentos.channel_hub.webchat_connector import WebChatConnector
        from fastapi import WebSocketDisconnect

        mock_router = AsyncMock()
        connector = WebChatConnector(agent_name="test-agent", router=mock_router)

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=WebSocketDisconnect())

        await connector.handle_websocket(mock_ws)

        # After disconnect, connections dict should be empty
        assert len(connector._connections) == 0

    @pytest.mark.asyncio
    async def test_response_includes_buttons_and_images(self):
        from tinyagentos.channel_hub.webchat_connector import WebChatConnector

        response = OutgoingMessage(
            content="Here you go",
            buttons=[{"label": "OK", "action": "ok"}],
            images=["http://example.com/img.png"],
        )
        mock_router = AsyncMock()
        mock_router.route_message = AsyncMock(return_value=response)

        connector = WebChatConnector(agent_name="test-agent", router=mock_router)

        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.receive_text = AsyncMock(
            side_effect=[json.dumps({"text": "show"}), Exception("done")]
        )
        mock_ws.send_text = AsyncMock()

        await connector.handle_websocket(mock_ws)

        sent_data = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent_data["content"] == "Here you go"
        assert len(sent_data["buttons"]) == 1
        assert len(sent_data["images"]) == 1
        assert "timestamp" in sent_data


# ---------------------------------------------------------------------------
# Framework Adapter health endpoints (import and structure tests)
# ---------------------------------------------------------------------------

class TestAdapterStructure:
    def test_pocketflow_adapter_has_health(self):
        """PocketFlow adapter module has /health endpoint."""
        from tinyagentos.adapters.pocketflow_adapter import app
        routes = [r.path for r in app.routes]
        assert "/health" in routes
        assert "/message" in routes

    def test_openclaw_adapter_has_health(self):
        """OpenClaw adapter module has /health endpoint."""
        from tinyagentos.adapters.openclaw_adapter import app
        routes = [r.path for r in app.routes]
        assert "/health" in routes
        assert "/message" in routes

    def test_langroid_adapter_has_health(self):
        """Langroid adapter module has /health endpoint."""
        from tinyagentos.adapters.langroid_adapter import app
        routes = [r.path for r in app.routes]
        assert "/health" in routes
        assert "/message" in routes

    def test_swarm_adapter_has_health(self):
        """Swarm adapter module has /health endpoint."""
        from tinyagentos.adapters.swarm_adapter import app
        routes = [r.path for r in app.routes]
        assert "/health" in routes
        assert "/message" in routes

    def test_generic_adapter_has_health(self):
        """Verify existing generic adapter still works."""
        from tinyagentos.adapters.generic_adapter import app
        routes = [r.path for r in app.routes]
        assert "/health" in routes
        assert "/message" in routes

    def test_smolagents_adapter_has_health(self):
        """Verify existing smolagents adapter still works."""
        from tinyagentos.adapters.smolagents_adapter import app
        routes = [r.path for r in app.routes]
        assert "/health" in routes
        assert "/message" in routes


# ---------------------------------------------------------------------------
# Channel Hub API — Discord and WebChat connect endpoints
# ---------------------------------------------------------------------------

class TestChannelHubAPINew:
    @pytest.mark.asyncio
    async def test_connect_discord_secret_not_found(self, client):
        resp = await client.post("/api/channel-hub/connect", json={
            "platform": "discord",
            "bot_token_secret": "nonexistent_discord_secret",
            "agent_name": "test-agent",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_connect_webchat_no_agent_name(self, client):
        resp = await client.post("/api/channel-hub/connect", json={
            "platform": "webchat",
        })
        assert resp.status_code == 400
        assert "agent_name" in resp.json()["error"]

    @pytest.mark.asyncio
    async def test_connect_webchat_success(self, client):
        resp = await client.post("/api/channel-hub/connect", json={
            "platform": "webchat",
            "agent_name": "chat-agent",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "connected"
        assert data["platform"] == "webchat"
        assert data["agent_name"] == "chat-agent"

    @pytest.mark.asyncio
    async def test_webchat_page_renders(self, client):
        resp = await client.get("/chat/my-agent")
        assert resp.status_code == 200
        text = resp.text
        assert "my-agent" in text
        assert "Chat" in text
        # Check ARIA labels
        assert 'aria-label="Chat interface"' in text or 'aria-label="Chat messages"' in text

    @pytest.mark.asyncio
    async def test_disconnect_webchat(self, client):
        # Connect first
        await client.post("/api/channel-hub/connect", json={
            "platform": "webchat",
            "agent_name": "temp-agent",
        })
        # Disconnect
        resp = await client.post("/api/channel-hub/disconnect", json={
            "platform": "webchat",
            "agent_name": "temp-agent",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "disconnected"

    @pytest.mark.asyncio
    async def test_status_shows_webchat_connector(self, client):
        await client.post("/api/channel-hub/connect", json={
            "platform": "webchat",
            "agent_name": "status-agent",
        })
        resp = await client.get("/api/channel-hub/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "webchat:status-agent" in data["connectors"]
        connector_info = data["connectors"]["webchat:status-agent"]
        assert connector_info["platform"] == "webchat"

    @pytest.mark.asyncio
    async def test_connect_unsupported_platform_still_fails(self, client):
        await client.post("/api/secrets", json={"name": "irc_token", "value": "fake"})
        resp = await client.post("/api/channel-hub/connect", json={
            "platform": "irc",
            "bot_token_secret": "irc_token",
            "agent_name": "test-agent",
        })
        assert resp.status_code == 400
        assert "not yet supported" in resp.json()["error"]
