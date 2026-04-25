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


@pytest.mark.asyncio
async def test_create_and_list_tasks(client):
    pid = (await client.post("/api/projects", json={"name": "A", "slug": "a"})).json()["id"]

    resp = await client.post(
        f"/api/projects/{pid}/tasks",
        json={"title": "T1", "body": "do it", "priority": 2},
    )
    assert resp.status_code == 200
    t = resp.json()
    assert t["id"].startswith("tsk-")

    resp = await client.get(f"/api/projects/{pid}/tasks")
    assert [x["id"] for x in resp.json()["items"]] == [t["id"]]


@pytest.mark.asyncio
async def test_ready_endpoint(client):
    pid = (await client.post("/api/projects", json={"name": "A", "slug": "a"})).json()["id"]
    a = (await client.post(f"/api/projects/{pid}/tasks", json={"title": "A"})).json()
    b = (await client.post(f"/api/projects/{pid}/tasks", json={"title": "B"})).json()
    await client.post(
        f"/api/projects/{pid}/tasks/{a['id']}/relationships",
        json={"to_task_id": b["id"], "kind": "blocks"},
    )
    resp = await client.get(f"/api/projects/{pid}/tasks/ready")
    assert [t["id"] for t in resp.json()["items"]] == [b["id"]]


@pytest.mark.asyncio
async def test_claim_release_close(client):
    pid = (await client.post("/api/projects", json={"name": "A", "slug": "a"})).json()["id"]
    t = (await client.post(f"/api/projects/{pid}/tasks", json={"title": "A"})).json()

    resp = await client.post(f"/api/projects/{pid}/tasks/{t['id']}/claim", json={"claimer_id": "agent-1"})
    assert resp.status_code == 200
    assert resp.json()["claimed_by"] == "agent-1"

    resp = await client.post(f"/api/projects/{pid}/tasks/{t['id']}/claim", json={"claimer_id": "agent-2"})
    assert resp.status_code == 409

    resp = await client.post(f"/api/projects/{pid}/tasks/{t['id']}/release", json={"releaser_id": "agent-1"})
    assert resp.status_code == 200

    await client.post(f"/api/projects/{pid}/tasks/{t['id']}/claim", json={"claimer_id": "agent-1"})
    resp = await client.post(
        f"/api/projects/{pid}/tasks/{t['id']}/close",
        json={"closed_by": "agent-1", "reason": "done"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_threaded_comments_route(client):
    pid = (await client.post("/api/projects", json={"name": "A", "slug": "a"})).json()["id"]
    t = (await client.post(f"/api/projects/{pid}/tasks", json={"title": "T"})).json()

    resp = await client.post(
        f"/api/projects/{pid}/tasks/{t['id']}/comments",
        json={"body": "root", "author_id": "u"},
    )
    assert resp.status_code == 200
    c1 = resp.json()

    resp = await client.post(
        f"/api/projects/{pid}/tasks/{t['id']}/comments",
        json={"body": "reply", "author_id": "u2", "replies_to_comment_id": c1["id"]},
    )
    assert resp.json()["replies_to_comment_id"] == c1["id"]

    resp = await client.get(f"/api/projects/{pid}/tasks/{t['id']}/comments")
    assert len(resp.json()["items"]) == 2


@pytest.mark.asyncio
async def test_list_relationships_route(client):
    pid = (await client.post("/api/projects", json={"name": "A", "slug": "a"})).json()["id"]
    a = (await client.post(f"/api/projects/{pid}/tasks", json={"title": "A"})).json()
    b = (await client.post(f"/api/projects/{pid}/tasks", json={"title": "B"})).json()
    await client.post(
        f"/api/projects/{pid}/tasks/{a['id']}/relationships",
        json={"to_task_id": b["id"], "kind": "blocks"},
    )
    resp = await client.get(f"/api/projects/{pid}/tasks/{a['id']}/relationships")
    assert [r["to_task_id"] for r in resp.json()["items"]] == [b["id"]]


@pytest.mark.asyncio
async def test_activity_feed(client):
    resp = await client.post("/api/projects", json={"name": "A", "slug": "a"})
    pid = resp.json()["id"]
    await client.post(f"/api/projects/{pid}/members", json={"mode": "native", "agent_id": "agent-1"})
    await client.post(f"/api/projects/{pid}/tasks", json={"title": "T"})

    resp = await client.get(f"/api/projects/{pid}/activity")
    assert resp.status_code == 200
    kinds = [item["kind"] for item in resp.json()["items"]]
    assert "project.created" in kinds
    assert "member.added" in kinds
    assert "task.created" in kinds
