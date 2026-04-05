import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from tinyagentos.app import create_app

# Import the helper to create test QMD databases
from test_qmd_db import create_test_qmd_db


@pytest.fixture
def app_with_qmd(tmp_data_dir, tmp_path, monkeypatch):
    qmd_cache = tmp_path / "qmd_cache"
    qmd_cache.mkdir()
    create_test_qmd_db(qmd_cache / "test.sqlite")

    app = create_app(data_dir=tmp_data_dir)

    # Monkeypatch QMD_CACHE_DIR in both dashboard and memory routes
    import tinyagentos.routes.dashboard as dashboard_mod
    import tinyagentos.routes.memory as memory_mod
    monkeypatch.setattr(dashboard_mod, "QMD_CACHE_DIR", qmd_cache)
    monkeypatch.setattr(memory_mod, "QMD_CACHE_DIR", qmd_cache)

    return app


@pytest_asyncio.fixture
async def client(app_with_qmd):
    app_with_qmd.state.metrics._db = None
    await app_with_qmd.state.metrics.init()
    transport = ASGITransport(app=app_with_qmd)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
class TestMemoryPage:
    async def test_memory_page_returns_html(self, client):
        resp = await client.get("/memory")
        assert resp.status_code == 200
        assert "Memory" in resp.text

    async def test_browse_returns_chunks(self, client):
        resp = await client.get("/api/memory/browse?agent=test-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["chunks"]) == 3

    async def test_browse_by_collection(self, client):
        resp = await client.get("/api/memory/browse?agent=test-agent&collection=transcripts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["chunks"]) == 2

    async def test_keyword_search(self, client):
        resp = await client.post("/api/memory/search", json={
            "query": "roadmap", "mode": "keyword", "agent": "test-agent",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) >= 1

    async def test_collections_endpoint(self, client):
        resp = await client.get("/api/memory/collections/test-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_delete_chunk(self, client):
        resp = await client.delete("/api/memory/chunk/abc123?agent=test-agent")
        assert resp.status_code == 200
        resp2 = await client.get("/api/memory/browse?agent=test-agent")
        assert len(resp2.json()["chunks"]) == 2
