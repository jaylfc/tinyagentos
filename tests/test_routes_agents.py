import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from tinyagentos.app import create_app
from tinyagentos.config import load_config

@pytest.fixture
def app(tmp_data_dir):
    return create_app(data_dir=tmp_data_dir)

@pytest_asyncio.fixture
async def client(app):
    app.state.metrics._db = None
    await app.state.metrics.init()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
class TestAgentsPage:
    async def test_agents_page_returns_html(self, client):
        resp = await client.get("/agents")
        assert resp.status_code == 200
        assert "Agents" in resp.text

    async def test_list_agents_api(self, client):
        resp = await client.get("/api/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test-agent"

    async def test_add_agent(self, client, tmp_data_dir):
        resp = await client.post("/api/agents", json={
            "name": "new-agent", "host": "10.0.0.5", "qmd_index": "new", "color": "#ff0000",
        })
        assert resp.status_code == 200
        config = load_config(tmp_data_dir / "config.yaml")
        assert len(config.agents) == 2

    async def test_update_agent(self, client, tmp_data_dir):
        resp = await client.put("/api/agents/test-agent", json={"host": "10.0.0.99"})
        assert resp.status_code == 200
        config = load_config(tmp_data_dir / "config.yaml")
        assert config.agents[0]["host"] == "10.0.0.99"

    async def test_delete_agent(self, client, tmp_data_dir):
        resp = await client.delete("/api/agents/test-agent")
        assert resp.status_code == 200
        config = load_config(tmp_data_dir / "config.yaml")
        assert len(config.agents) == 0

    async def test_add_duplicate_agent_fails(self, client):
        resp = await client.post("/api/agents", json={
            "name": "test-agent", "host": "10.0.0.1", "qmd_index": "dup", "color": "#000",
        })
        assert resp.status_code == 409
