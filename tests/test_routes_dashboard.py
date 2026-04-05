import pytest


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
