import pytest
import pytest_asyncio

from tinyagentos.projects.project_store import ProjectStore


@pytest_asyncio.fixture
async def store(tmp_path):
    s = ProjectStore(tmp_path / "projects.db")
    await s.init()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_create_and_get_project(store):
    p = await store.create_project(
        name="Tax Prep 2026",
        slug="tax-prep-2026",
        description="annual filing",
        created_by="user-1",
    )
    assert p["id"].startswith("prj-")
    assert p["name"] == "Tax Prep 2026"
    assert p["slug"] == "tax-prep-2026"
    assert p["status"] == "active"
    assert p["created_by"] == "user-1"

    again = await store.get_project(p["id"])
    assert again == p


@pytest.mark.asyncio
async def test_create_project_rejects_duplicate_slug(store):
    await store.create_project(name="A", slug="dup", created_by="u")
    with pytest.raises(ValueError):
        await store.create_project(name="B", slug="dup", created_by="u")


@pytest.mark.asyncio
async def test_list_projects_filter_by_status(store):
    a = await store.create_project(name="A", slug="a", created_by="u")
    b = await store.create_project(name="B", slug="b", created_by="u")
    await store.set_status(b["id"], "archived")

    active = await store.list_projects(status="active")
    archived = await store.list_projects(status="archived")
    assert [p["id"] for p in active] == [a["id"]]
    assert [p["id"] for p in archived] == [b["id"]]


@pytest.mark.asyncio
async def test_update_project(store):
    p = await store.create_project(name="A", slug="a", created_by="u")
    await store.update_project(p["id"], name="A2", description="hello")
    again = await store.get_project(p["id"])
    assert again["name"] == "A2"
    assert again["description"] == "hello"
    assert again["updated_at"] >= p["updated_at"]


@pytest.mark.asyncio
async def test_add_remove_member(store):
    p = await store.create_project(name="A", slug="a", created_by="u")
    await store.add_member(
        p["id"],
        member_id="agent-1",
        member_kind="native",
        role="member",
    )
    await store.add_member(
        p["id"],
        member_id="agent-2-clone",
        member_kind="clone",
        source_agent_id="agent-2",
        memory_seed="snapshot",
    )
    members = await store.list_members(p["id"])
    assert len(members) == 2
    by_id = {m["member_id"]: m for m in members}
    assert by_id["agent-2-clone"]["memory_seed"] == "snapshot"
    assert by_id["agent-2-clone"]["source_agent_id"] == "agent-2"

    await store.remove_member(p["id"], "agent-1")
    members = await store.list_members(p["id"])
    assert [m["member_id"] for m in members] == ["agent-2-clone"]


@pytest.mark.asyncio
async def test_log_activity(store):
    p = await store.create_project(name="A", slug="a", created_by="u")
    await store.log_activity(p["id"], actor_id="u", kind="project.created", payload={"name": "A"})
    await store.log_activity(p["id"], actor_id="u", kind="member.added", payload={"member_id": "agent-1"})
    rows = await store.list_activity(p["id"])
    assert [r["kind"] for r in rows] == ["member.added", "project.created"]
    assert rows[0]["payload"] == {"member_id": "agent-1"}
