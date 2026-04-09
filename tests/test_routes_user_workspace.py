"""Tests for the user workspace file browser routes."""
import io
import pytest


class TestUserWorkspaceRoutes:

    @pytest.mark.asyncio
    async def test_workspace_page_returns_200(self, client):
        """GET /workspace returns an HTML page."""
        resp = await client.get("/workspace")
        assert resp.status_code == 200
        assert "Workspace" in resp.text

    @pytest.mark.asyncio
    async def test_list_files_empty(self, client):
        """Listing files in an empty workspace returns an empty list."""
        resp = await client.get("/api/workspace/files")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_upload_file(self, client):
        """Uploading a file returns status uploaded and the file name."""
        content = b"hello workspace"
        resp = await client.post(
            "/api/workspace/files/upload",
            files={"file": ("hello.txt", io.BytesIO(content), "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "hello.txt"
        assert data["size"] == len(content)
        assert data["status"] == "uploaded"

    @pytest.mark.asyncio
    async def test_upload_and_list(self, client):
        """Uploaded file appears in file listing."""
        content = b"list me"
        await client.post(
            "/api/workspace/files/upload",
            files={"file": ("list_me.txt", io.BytesIO(content), "text/plain")},
        )
        resp = await client.get("/api/workspace/files")
        assert resp.status_code == 200
        names = [e["name"] for e in resp.json()]
        assert "list_me.txt" in names

    @pytest.mark.asyncio
    async def test_create_directory(self, client):
        """POST /api/workspace/mkdir creates a directory."""
        resp = await client.post("/api/workspace/mkdir", json={"path": "mydir"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert "mydir" in data["path"]

    @pytest.mark.asyncio
    async def test_list_subdirectory(self, client):
        """Files uploaded into a subdirectory appear when listing that subdir."""
        # Create subdir
        await client.post("/api/workspace/mkdir", json={"path": "subdir"})
        # Upload into subdir
        content = b"subdir file"
        await client.post(
            "/api/workspace/files/upload?path=subdir",
            files={"file": ("sub.txt", io.BytesIO(content), "text/plain")},
        )
        # List subdir
        resp = await client.get("/api/workspace/files?path=subdir")
        assert resp.status_code == 200
        names = [e["name"] for e in resp.json()]
        assert "sub.txt" in names

    @pytest.mark.asyncio
    async def test_delete_file(self, client):
        """Deleting an uploaded file returns status deleted and removes it from listing."""
        content = b"delete me"
        await client.post(
            "/api/workspace/files/upload",
            files={"file": ("to_delete.txt", io.BytesIO(content), "text/plain")},
        )
        # Verify it exists
        list_resp = await client.get("/api/workspace/files")
        names = [e["name"] for e in list_resp.json()]
        assert "to_delete.txt" in names

        # Delete it
        del_resp = await client.delete("/api/workspace/files/to_delete.txt")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "deleted"

        # Verify gone
        list_resp2 = await client.get("/api/workspace/files")
        names2 = [e["name"] for e in list_resp2.json()]
        assert "to_delete.txt" not in names2

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, client):
        """Deleting a file that does not exist returns 404."""
        resp = await client.delete("/api/workspace/files/ghost_file.txt")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, client):
        """Path traversal attempts are blocked with 400."""
        resp = await client.get("/api/workspace/files?path=../../etc")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_storage_stats(self, client):
        """GET /api/workspace/stats returns total_files and total_size."""
        # Upload a file so stats are non-trivial
        content = b"stats check"
        await client.post(
            "/api/workspace/files/upload",
            files={"file": ("stats.txt", io.BytesIO(content), "text/plain")},
        )
        resp = await client.get("/api/workspace/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_files" in data
        assert "total_size" in data
        assert data["total_files"] >= 1
        assert data["total_size"] >= len(content)
