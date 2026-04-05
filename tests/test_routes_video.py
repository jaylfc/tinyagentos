import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Request as HttpxRequest, Response

from tinyagentos.app import create_app


@pytest.fixture
def video_app(tmp_data_dir):
    app = create_app(data_dir=tmp_data_dir)
    app.state.data_dir = str(tmp_data_dir)
    (tmp_data_dir / "videos").mkdir(exist_ok=True)
    return app


@pytest_asyncio.fixture
async def video_client(video_app):
    store = video_app.state.metrics
    if store._db is not None:
        await store.close()
    await store.init()
    await video_app.state.qmd_client.init()
    transport = ASGITransport(app=video_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await store.close()
    await video_app.state.qmd_client.close()
    await video_app.state.http_client.aclose()


@pytest.mark.asyncio
class TestVideoPage:
    async def test_video_page_returns_html(self, video_client):
        resp = await video_client.get("/video")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Video Generation" in resp.text

    async def test_video_page_has_active_nav(self, video_client):
        resp = await video_client.get("/video")
        assert 'class="active"' in resp.text

    async def test_video_page_has_generate_form(self, video_client):
        resp = await video_client.get("/video")
        assert "video-generate-form" in resp.text
        assert "wan2.1-1.3b" in resp.text

    async def test_video_page_has_nav_link(self, video_client):
        resp = await video_client.get("/video")
        assert 'href="/video"' in resp.text


@pytest.mark.asyncio
class TestVideoGenerate:
    async def test_generate_no_backend_returns_503(self, tmp_data_dir):
        """If no video backend is configured, return 503."""
        import yaml
        config_path = tmp_data_dir / "config.yaml"
        config = yaml.safe_load(config_path.read_text())
        config["backends"] = []
        config_path.write_text(yaml.dump(config))

        app = create_app(data_dir=tmp_data_dir)
        app.state.data_dir = str(tmp_data_dir)
        store = app.state.metrics
        if store._db is not None:
            await store.close()
        await store.init()
        await app.state.qmd_client.init()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/api/video/generate", json={"prompt": "test"})
        assert resp.status_code == 503
        assert "error" in resp.json()
        await store.close()
        await app.state.qmd_client.close()
        await app.state.http_client.aclose()

    async def test_generate_with_mocked_backend_b64(self, video_app, video_client):
        """Generate a video using a mocked backend returning base64 data."""
        import base64

        # Set video_backend_url in config
        video_app.state.config.server["video_backend_url"] = "http://localhost:9000"

        fake_mp4 = base64.b64encode(b"fake-mp4-data").decode()
        mock_request = HttpxRequest("POST", "http://localhost:9000/v1/videos/generations")
        mock_response = Response(
            status_code=200,
            json={"data": [{"b64_json": fake_mp4}]},
            request=mock_request,
        )

        with patch("tinyagentos.routes.video.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            resp = await video_client.post("/api/video/generate", json={
                "prompt": "a test video",
                "seed": 99,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "generated"
        assert data["prompt"] == "a test video"
        assert data["seed"] == 99
        assert data["filename"].endswith("_99.mp4")

        # Verify file was saved
        videos_dir = video_app.state.config.config_path.parent / "videos"
        saved_files = list(videos_dir.glob("*.mp4"))
        assert len(saved_files) == 1
        assert saved_files[0].read_bytes() == b"fake-mp4-data"

        # Verify metadata sidecar
        meta_files = list(videos_dir.glob("*.json"))
        assert len(meta_files) == 1
        meta = json.loads(meta_files[0].read_text())
        assert meta["prompt"] == "a test video"

        # Cleanup config mutation
        del video_app.state.config.server["video_backend_url"]

    async def test_generate_connection_error(self, video_app, video_client):
        video_app.state.config.server["video_backend_url"] = "http://localhost:9000"

        with patch("tinyagentos.routes.video.httpx.AsyncClient") as MockClient:
            import httpx as real_httpx
            mock_instance = AsyncMock()
            mock_instance.post.side_effect = real_httpx.ConnectError("Connection refused")
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            resp = await video_client.post("/api/video/generate", json={"prompt": "test"})

        assert resp.status_code == 503
        assert "Cannot connect" in resp.json()["error"]

        del video_app.state.config.server["video_backend_url"]

    async def test_generate_timeout_error(self, video_app, video_client):
        video_app.state.config.server["video_backend_url"] = "http://localhost:9000"

        with patch("tinyagentos.routes.video.httpx.AsyncClient") as MockClient:
            import httpx as real_httpx
            mock_instance = AsyncMock()
            mock_instance.post.side_effect = real_httpx.TimeoutException("Timeout")
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            resp = await video_client.post("/api/video/generate", json={"prompt": "test"})

        assert resp.status_code == 504
        assert "timed out" in resp.json()["error"]

        del video_app.state.config.server["video_backend_url"]

    async def test_generate_bad_response_format(self, video_app, video_client):
        video_app.state.config.server["video_backend_url"] = "http://localhost:9000"

        mock_request = HttpxRequest("POST", "http://localhost:9000/v1/videos/generations")
        mock_response = Response(
            status_code=200,
            json={"unexpected": "format"},
            request=mock_request,
        )

        with patch("tinyagentos.routes.video.httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_instance

            resp = await video_client.post("/api/video/generate", json={"prompt": "test"})

        assert resp.status_code == 502
        assert "Unexpected response format" in resp.json()["error"]

        del video_app.state.config.server["video_backend_url"]


@pytest.mark.asyncio
class TestVideoList:
    async def test_list_empty(self, video_client):
        resp = await video_client.get("/api/video")
        assert resp.status_code == 200
        data = resp.json()
        assert data["videos"] == []

    async def test_list_with_videos(self, video_app, video_client):
        videos_dir = video_app.state.config.config_path.parent / "videos"
        videos_dir.mkdir(exist_ok=True)
        (videos_dir / "1234_42.mp4").write_bytes(b"fake-mp4")
        (videos_dir / "1234_42.json").write_text(json.dumps({
            "prompt": "hello world", "model": "wan2.1-1.3b",
            "duration": 5, "resolution": "480x832", "seed": 42,
        }))

        resp = await video_client.get("/api/video")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["videos"]) == 1
        assert data["videos"][0]["prompt"] == "hello world"
        assert data["videos"][0]["filename"] == "1234_42.mp4"
        assert data["videos"][0]["seed"] == 42


@pytest.mark.asyncio
class TestVideoDelete:
    async def test_delete_nonexistent(self, video_client):
        resp = await video_client.delete("/api/video/nonexistent.mp4")
        assert resp.status_code == 404

    async def test_delete_video(self, video_app, video_client):
        videos_dir = video_app.state.config.config_path.parent / "videos"
        videos_dir.mkdir(exist_ok=True)
        (videos_dir / "1234_42.mp4").write_bytes(b"fake-mp4")
        (videos_dir / "1234_42.json").write_text('{"prompt": "test"}')

        resp = await video_client.delete("/api/video/1234_42.mp4")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"
        assert data["filename"] == "1234_42.mp4"

        assert not (videos_dir / "1234_42.mp4").exists()
        assert not (videos_dir / "1234_42.json").exists()

    async def test_delete_path_traversal(self, video_client):
        resp = await video_client.delete("/api/video/..%2F..%2Fetc%2Fpasswd")
        assert resp.status_code in (400, 404)

    async def test_delete_invalid_filename_backslash(self, video_client):
        resp = await video_client.delete("/api/video/foo%5Cbar.mp4")
        assert resp.status_code in (400, 404)
