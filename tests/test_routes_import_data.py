import io
import pytest


class TestImportDataRoutes:
    @pytest.mark.asyncio
    async def test_import_page(self, client):
        resp = await client.get("/import")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_upload_text_file(self, client):
        file_content = b"This is a test document for import."
        resp = await client.post(
            "/api/import/upload",
            files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_embed_files(self, client):
        # Upload a file first, then embed it
        content = b"Content to embed for import data test."
        await client.post(
            "/api/import/upload",
            files={"file": ("import_data_test.txt", io.BytesIO(content), "text/plain")},
        )
        resp = await client.post("/api/import/embed", json={
            "agent_name": "test-agent",
            "files": ["import_data_test.txt"],
        })
        assert resp.status_code == 200
        assert "status" in resp.json()

    @pytest.mark.asyncio
    async def test_embed_files_returns_embedded_field(self, client):
        # Upload a file first
        content = b"Content to check embedded field in response."
        await client.post(
            "/api/import/upload",
            files={"file": ("embed_field_test.txt", io.BytesIO(content), "text/plain")},
        )
        resp = await client.post("/api/import/embed", json={
            "agent_name": "test-agent",
            "files": ["embed_field_test.txt"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "embedded" in data
        # No real QMD server in tests — embedded should be False
        assert data["embedded"] is False
        # Each file entry should also carry an embedded bool
        assert len(data["files"]) == 1
        assert "embedded" in data["files"][0]
        assert data["files"][0]["embedded"] is False

    @pytest.mark.asyncio
    async def test_upload_no_file(self, client):
        resp = await client.post("/api/import/upload")
        assert resp.status_code in (400, 422)
