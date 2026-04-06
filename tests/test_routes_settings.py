import pytest


class TestSettingsRoutes:
    @pytest.mark.asyncio
    async def test_settings_page(self, client):
        resp = await client.get("/settings")
        assert resp.status_code == 200
        assert b"Settings" in resp.content or b"settings" in resp.content

    @pytest.mark.asyncio
    async def test_get_config(self, client):
        resp = await client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "yaml" in data

    @pytest.mark.asyncio
    async def test_get_storage(self, client):
        resp = await client.get("/api/settings/storage")
        assert resp.status_code == 200
        data = resp.json()
        assert "storage" in data

    @pytest.mark.asyncio
    async def test_save_platform_settings(self, client):
        resp = await client.put("/api/settings/platform", json={
            "poll_interval": 60,
            "retention_days": 14,
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

    @pytest.mark.asyncio
    async def test_llm_proxy_status(self, client):
        resp = await client.get("/api/settings/llm-proxy")
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data
        assert "port" in data

    @pytest.mark.asyncio
    async def test_get_notification_prefs(self, client):
        resp = await client.get("/api/settings/notification-prefs")
        assert resp.status_code == 200
        data = resp.json()
        assert "prefs" in data
        assert isinstance(data["prefs"], list)
        assert len(data["prefs"]) > 0
        assert "event_type" in data["prefs"][0]
        assert "muted" in data["prefs"][0]

    @pytest.mark.asyncio
    async def test_toggle_notification_pref(self, client):
        resp = await client.post(
            "/api/settings/notification-prefs/worker.join",
            json={"muted": True},
        )
        assert resp.status_code == 200
        assert resp.json()["muted"] is True
        # Verify it persisted
        resp = await client.get("/api/settings/notification-prefs")
        prefs = resp.json()["prefs"]
        worker_join = [p for p in prefs if p["event_type"] == "worker.join"]
        assert worker_join[0]["muted"] is True

    @pytest.mark.asyncio
    async def test_webhooks_crud(self, client):
        resp = await client.post("/api/settings/webhooks", json={
            "url": "https://example.com/hook",
            "type": "generic",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "added"
        resp = await client.get("/api/settings/webhooks")
        assert resp.status_code == 200
        assert len(resp.json()["webhooks"]) == 1
        resp = await client.delete("/api/settings/webhooks/0")
        assert resp.status_code == 200
        assert resp.json()["status"] == "removed"
