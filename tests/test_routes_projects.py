import pytest


@pytest.mark.asyncio
async def test_create_and_list_project(client):
    resp = await client.post("/api/projects", json={"name": "Alpha", "slug": "alpha", "description": "x"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"].startswith("prj-")
    assert body["slug"] == "alpha"

    resp = await client.get("/api/projects")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(p["slug"] == "alpha" for p in items)


@pytest.mark.asyncio
async def test_create_project_duplicate_slug_returns_409(client):
    await client.post("/api/projects", json={"name": "A", "slug": "dup"})
    resp = await client.post("/api/projects", json={"name": "B", "slug": "dup"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_update_delete_project(client):
    resp = await client.post("/api/projects", json={"name": "A", "slug": "a"})
    pid = resp.json()["id"]

    resp = await client.get(f"/api/projects/{pid}")
    assert resp.status_code == 200

    resp = await client.patch(f"/api/projects/{pid}", json={"name": "A2"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "A2"

    resp = await client.post(f"/api/projects/{pid}/archive")
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"

    resp = await client.delete(f"/api/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_add_native_member(client):
    resp = await client.post("/api/projects", json={"name": "A", "slug": "a"})
    pid = resp.json()["id"]

    resp = await client.post(
        f"/api/projects/{pid}/members",
        json={"mode": "native", "agent_id": "agent-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["member_kind"] == "native"
    assert body["member_id"] == "agent-1"

    resp = await client.get(f"/api/projects/{pid}/members")
    assert any(m["member_id"] == "agent-1" for m in resp.json()["items"])


@pytest.mark.asyncio
async def test_add_clone_member_with_memory_seed(client):
    resp = await client.post("/api/projects", json={"name": "A", "slug": "a"})
    pid = resp.json()["id"]

    resp = await client.post(
        f"/api/projects/{pid}/members",
        json={"mode": "clone", "source_agent_id": "agent-1", "clone_memory": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["member_kind"] == "clone"
    assert body["source_agent_id"] == "agent-1"
    assert body["memory_seed"] == "snapshot"
    assert body["member_id"] == "agent-1-a"


@pytest.mark.asyncio
async def test_add_clone_member_empty_memory(client):
    resp = await client.post("/api/projects", json={"name": "A", "slug": "a"})
    pid = resp.json()["id"]

    resp = await client.post(
        f"/api/projects/{pid}/members",
        json={"mode": "clone", "source_agent_id": "agent-1", "clone_memory": False},
    )
    assert resp.json()["memory_seed"] == "empty"


@pytest.mark.asyncio
async def test_remove_member(client):
    resp = await client.post("/api/projects", json={"name": "A", "slug": "a"})
    pid = resp.json()["id"]
    await client.post(f"/api/projects/{pid}/members", json={"mode": "native", "agent_id": "agent-1"})

    resp = await client.delete(f"/api/projects/{pid}/members/agent-1")
    assert resp.status_code == 200

    resp = await client.get(f"/api/projects/{pid}/members")
    assert resp.json()["items"] == []
