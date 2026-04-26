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


@pytest.mark.asyncio
async def test_add_member_adds_to_a2a_channel(client):
    pid = (await client.post("/api/projects", json={"name": "P", "slug": "ra2a-2"})).json()["id"]

    res = await client.post(
        f"/api/projects/{pid}/members",
        json={"mode": "native", "agent_id": "agentA"},
    )
    assert res.status_code == 200

    channels = await _list_channels(client, pid)
    a2a = _a2a(channels)
    assert a2a is not None
    assert "agentA" in a2a["members"]


@pytest.mark.asyncio
async def test_remove_member_removes_from_a2a_channel(client):
    pid = (await client.post("/api/projects", json={"name": "P", "slug": "ra2a-3"})).json()["id"]
    await client.post(
        f"/api/projects/{pid}/members",
        json={"mode": "native", "agent_id": "agentA"},
    )

    res = await client.delete(f"/api/projects/{pid}/members/agentA")
    assert res.status_code == 200

    channels = await _list_channels(client, pid)
    a2a = _a2a(channels)
    assert a2a is not None
    assert "agentA" not in a2a["members"]


@pytest.mark.asyncio
async def test_a2a_failure_does_not_break_project_create(client, monkeypatch, caplog):
    import tinyagentos.projects.a2a as a2a_mod

    async def boom(*args, **kwargs):
        raise RuntimeError("simulated a2a failure")

    monkeypatch.setattr(a2a_mod, "ensure_a2a_channel", boom)

    with caplog.at_level("WARNING"):
        res = await client.post("/api/projects", json={"name": "P", "slug": "ra2a-fail"})
    assert res.status_code == 200
    assert res.json()["slug"] == "ra2a-fail"
    assert any("a2a ensure failed" in rec.message for rec in caplog.records)
