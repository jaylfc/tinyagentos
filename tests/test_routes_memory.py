import pytest


@pytest.mark.asyncio
class TestMemoryPage:
    async def test_memory_page_returns_html(self, client_with_qmd):
        resp = await client_with_qmd.get("/memory")
        assert resp.status_code == 200
        assert "Memory" in resp.text

    async def test_browse_returns_chunks(self, client_with_qmd):
        resp = await client_with_qmd.get("/api/memory/browse?agent=test-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["chunks"]) == 3

    async def test_browse_by_collection(self, client_with_qmd):
        resp = await client_with_qmd.get("/api/memory/browse?agent=test-agent&collection=transcripts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["chunks"]) == 2

    async def test_keyword_search(self, client_with_qmd):
        resp = await client_with_qmd.post("/api/memory/search", json={
            "query": "roadmap", "mode": "keyword", "agent": "test-agent",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) >= 1

    async def test_collections_endpoint(self, client_with_qmd):
        resp = await client_with_qmd.get("/api/memory/collections/test-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_delete_chunk(self, client_with_qmd):
        resp = await client_with_qmd.delete("/api/memory/chunk/abc123?agent=test-agent")
        assert resp.status_code == 200
        resp2 = await client_with_qmd.get("/api/memory/browse?agent=test-agent")
        assert len(resp2.json()["chunks"]) == 2
