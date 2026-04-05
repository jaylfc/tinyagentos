import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from tinyagentos.app import create_app


@pytest.fixture
def app(tmp_data_dir):
    return create_app(data_dir=tmp_data_dir)


@pytest_asyncio.fixture
async def client(app):
    """Async test client that initialises the metrics store before requests."""
    await app.state.metrics.init()
    await app.state.qmd_client.init()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await app.state.metrics.close()
    await app.state.qmd_client.close()
    await app.state.http_client.aclose()


@pytest.mark.asyncio
class TestHealthEndpoint:
    async def test_health_returns_ok(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data


@pytest.mark.asyncio
class TestDashboardPage:
    async def test_dashboard_returns_html(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "TinyAgentOS" in resp.text

    async def test_backends_api(self, client):
        resp = await client.get("/api/backends")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_metrics_api(self, client):
        resp = await client.get("/api/metrics/test.metric?range=24h")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
