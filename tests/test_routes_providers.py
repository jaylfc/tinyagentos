import pytest

@pytest.mark.asyncio
class TestProviderAPI:
    async def test_list_providers(self, client):
        resp = await client.get("/api/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_test_connection_missing_url(self, client):
        resp = await client.post("/api/providers/test", json={"type": "ollama"})
        assert resp.status_code == 422  # Pydantic validation requires url field

    async def test_add_provider(self, client):
        resp = await client.post("/api/providers", json={
            "name": "test-ollama", "type": "ollama",
            "url": "http://localhost:11434", "priority": 1,
        })
        assert resp.status_code == 200

    async def test_delete_provider(self, client):
        # Add then delete
        await client.post("/api/providers", json={
            "name": "to-delete", "type": "ollama",
            "url": "http://localhost:11434", "priority": 5,
        })
        resp = await client.delete("/api/providers/to-delete")
        assert resp.status_code == 200

    async def test_providers_page_renders(self, client):
        resp = await client.get("/providers")
        assert resp.status_code == 200
        assert "Provider" in resp.text

    async def test_add_duplicate_provider(self, client):
        await client.post("/api/providers", json={
            "name": "dup-test", "type": "ollama",
            "url": "http://localhost:11434", "priority": 1,
        })
        resp = await client.post("/api/providers", json={
            "name": "dup-test", "type": "ollama",
            "url": "http://localhost:11434", "priority": 2,
        })
        assert resp.status_code == 409
