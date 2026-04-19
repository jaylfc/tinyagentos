import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_get_framework_state(client, app):
    app.state.config.agents.append({
        "name": "atlas-fw", "framework": "openclaw",
        "framework_version_tag": "T1", "framework_version_sha": "a1a1a1a",
        "framework_update_status": "idle",
    })
    app.state.latest_framework_versions = {
        "openclaw": {"tag": "T2", "sha": "b2b2b2b", "published_at": "x", "asset_url": "u"},
    }
    r = await client.get("/api/agents/atlas-fw/framework")
    assert r.status_code == 200
    body = r.json()
    assert body["framework"] == "openclaw"
    assert body["installed"]["sha"] == "a1a1a1a"
    assert body["latest"]["sha"] == "b2b2b2b"
    assert body["update_available"] is True
    assert body["update_status"] == "idle"


@pytest.mark.asyncio
async def test_get_framework_404(client):
    r = await client.get("/api/agents/nope-fw/framework")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_framework_no_latest_when_source_missing(client, app):
    app.state.config.agents.append({
        "name": "bob-fw", "framework": "legacy",
        "framework_version_tag": None, "framework_version_sha": None,
        "framework_update_status": "idle",
    })
    app.state.latest_framework_versions = {}
    r = await client.get("/api/agents/bob-fw/framework")
    assert r.json()["latest"] is None
    assert r.json()["update_available"] is False
