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
