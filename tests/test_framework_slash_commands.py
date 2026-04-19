import pytest


@pytest.mark.asyncio
async def test_slash_commands_endpoint_returns_per_slug_manifest(client, app):
    app.state.config.agents.append({
        "name": "tom", "framework": "hermes", "host": "localhost", "color": "#fff",
    })
    r = await client.get("/api/frameworks/slash-commands")
    assert r.status_code == 200
    body = r.json()
    # Shape: {slug: [{name, description}, ...]}
    assert "tom" in body
    assert isinstance(body["tom"], list)
    assert body["tom"][0]["name"] in ("help", "clear", "model")


@pytest.mark.asyncio
async def test_slash_commands_endpoint_handles_unknown_framework(client, app):
    app.state.config.agents.append({
        "name": "mystery", "framework": "nonexistent-fw", "host": "localhost", "color": "#fff",
    })
    r = await client.get("/api/frameworks/slash-commands")
    assert r.status_code == 200
    body = r.json()
    assert body.get("mystery") == []
