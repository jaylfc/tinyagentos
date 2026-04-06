"""Tests for the 5 new framework adapters: microclaw, ironclaw, nullclaw, moltis, nemoclaw."""
import pytest
from httpx import ASGITransport, AsyncClient


ADAPTERS = [
    ("microclaw", "tinyagentos.adapters.microclaw_adapter"),
    ("ironclaw", "tinyagentos.adapters.ironclaw_adapter"),
    ("nullclaw", "tinyagentos.adapters.nullclaw_adapter"),
    ("moltis", "tinyagentos.adapters.moltis_adapter"),
    ("nemoclaw", "tinyagentos.adapters.nemoclaw_adapter"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("framework,module_path", ADAPTERS)
async def test_adapter_health(framework, module_path):
    import importlib
    mod = importlib.import_module(module_path)
    app = mod.app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["framework"] == framework


@pytest.mark.asyncio
@pytest.mark.parametrize("framework,module_path", ADAPTERS)
async def test_adapter_message_without_framework(framework, module_path):
    import importlib
    mod = importlib.import_module(module_path)
    app = mod.app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/message", json={"text": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert "not installed" in data["content"]
