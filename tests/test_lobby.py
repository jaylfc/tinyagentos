"""Tests for the Agent Lobby demo."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tinyagentos.lobby.agents import AGENTS
from tinyagentos.lobby.avatars import generate_avatar_svg
from tinyagentos.lobby.chat import ChatRoom


# ---- Avatar tests ----


def test_avatar_returns_valid_svg():
    svg = generate_avatar_svg("Marcus")
    assert svg.startswith("<svg")
    assert "</svg>" in svg
    assert "MA" in svg  # initials for Marcus


def test_avatar_deterministic():
    assert generate_avatar_svg("Priya") == generate_avatar_svg("Priya")


def test_avatar_different_for_different_names():
    assert generate_avatar_svg("Marcus") != generate_avatar_svg("Priya")


def test_avatar_custom_size():
    svg = generate_avatar_svg("Test", size=80)
    assert 'width="80"' in svg
    assert 'height="80"' in svg


def test_avatar_two_word_name():
    svg = generate_avatar_svg("Raj Kumar")
    assert "RK" in svg


# ---- Agent list tests ----


def test_agents_has_100_plus():
    assert len(AGENTS) >= 100


def test_agent_structure():
    agent = AGENTS[0]
    assert "name" in agent
    assert "role" in agent
    assert "avatar_seed" in agent
    assert "system_prompt" in agent


def test_agent_names_unique():
    names = [a["name"] for a in AGENTS]
    assert len(names) == len(set(names))


def test_agent_system_prompts_mention_tinyagentos():
    for agent in AGENTS:
        assert "TinyAgentOS" in agent["system_prompt"]


# ---- Route tests ----


@pytest.mark.asyncio
async def test_lobby_config_page(client):
    resp = await client.get("/lobby/")
    assert resp.status_code == 200
    assert "Agent Lobby" in resp.text
    assert "Launch Chat Room" in resp.text


@pytest.mark.asyncio
async def test_lobby_chat_page(client):
    resp = await client.get("/lobby/chat?agents=50&topic=Test")
    assert resp.status_code == 200
    assert "Agent Lobby" in resp.text
    assert "50" in resp.text
    assert "Test" in resp.text


@pytest.mark.asyncio
async def test_start_stop_endpoints(client):
    # Mock the ChatRoom so no real inference happens
    with patch("tinyagentos.lobby.routes.ChatRoom") as MockRoom:
        mock_instance = AsyncMock()
        mock_instance.start = AsyncMock()
        mock_instance.stop = AsyncMock()
        MockRoom.return_value = mock_instance

        resp = await client.post(
            "/lobby/start",
            json={"topic": "Test topic", "count": 10, "backend_url": "http://localhost:11434"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert data["agents"] == 10

    # Stop
    resp = await client.post("/lobby/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"


# ---- ChatRoom unit tests ----


def test_chatroom_init():
    room = ChatRoom(AGENTS[:10], "http://localhost:11434", "Test topic")
    assert room.backend_type == "ollama"
    assert len(room.agents) == 10
    assert room.running is False


def test_chatroom_openai_detection():
    room = ChatRoom(AGENTS[:5], "http://localhost:8000/v1", "Test")
    assert room.backend_type == "openai"


def test_chatroom_explicit_backend_type():
    room = ChatRoom(AGENTS[:5], "http://localhost:11434", "Test", backend_type="openai")
    assert room.backend_type == "openai"


def test_chatroom_subscribe_unsubscribe():
    room = ChatRoom(AGENTS[:5], "http://localhost:11434", "Test")
    q = room.subscribe()
    assert q in room._subscribers
    room.unsubscribe(q)
    assert q not in room._subscribers
