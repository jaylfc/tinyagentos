from __future__ import annotations

import pytest


async def _list_channels(client, project_id: str) -> list[dict]:
    res = await client.get(f"/api/chat/channels?project_id={project_id}")
    assert res.status_code == 200
    return res.json().get("channels", [])


def _a2a(channels: list[dict]) -> dict | None:
    for c in channels:
        if (c.get("settings") or {}).get("kind") == "a2a":
            return c
    return None


@pytest.mark.asyncio
async def test_create_project_creates_a2a_channel(client):
    res = await client.post("/api/projects", json={"name": "P", "slug": "ra2a-1"})
    assert res.status_code == 200
    pid = res.json()["id"]

    channels = await _list_channels(client, pid)
    a2a = _a2a(channels)
    assert a2a is not None
    assert a2a["name"] == "a2a"
    assert a2a["type"] == "group"
    assert a2a["members"] == []
