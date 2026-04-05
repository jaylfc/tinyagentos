import pytest
import yaml
from tinyagentos.config import load_config


@pytest.mark.asyncio
class TestConfigPage:
    async def test_config_page_returns_html(self, client):
        resp = await client.get("/config")
        assert resp.status_code == 200
        assert "Config" in resp.text

    async def test_get_config_api(self, client):
        resp = await client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "yaml" in data
        parsed = yaml.safe_load(data["yaml"])
        assert parsed["server"]["port"] == 8888

    async def test_save_valid_config(self, client, tmp_data_dir):
        new_yaml = yaml.dump({
            "server": {"host": "0.0.0.0", "port": 9999},
            "backends": [],
            "qmd": {"url": "http://localhost:7832"},
            "agents": [],
            "metrics": {"poll_interval": 60, "retention_days": 7},
        })
        resp = await client.put("/api/config", json={"yaml": new_yaml})
        assert resp.status_code == 200
        config = load_config(tmp_data_dir / "config.yaml")
        assert config.server["port"] == 9999

    async def test_save_invalid_yaml_fails(self, client):
        resp = await client.put("/api/config", json={"yaml": ": : : bad [["})
        assert resp.status_code == 400
        assert "error" in resp.json()

    async def test_save_invalid_config_fails(self, client):
        bad_config = yaml.dump({
            "server": {"host": "0.0.0.0", "port": 8888},
            "backends": [{"name": "bad", "type": "unsupported", "url": "http://x"}],
            "qmd": {"url": "http://localhost:7832"},
            "agents": [],
            "metrics": {"poll_interval": 30, "retention_days": 30},
        })
        resp = await client.put("/api/config", json={"yaml": bad_config})
        assert resp.status_code == 400
