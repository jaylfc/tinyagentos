import pytest
import pytest_asyncio

from tinyagentos.projects.task_store import ProjectTaskStore


@pytest_asyncio.fixture
async def store(tmp_path):
    s = ProjectTaskStore(tmp_path / "tasks.db")
    await s.init()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_create_and_get_task(store):
    t = await store.create_task(
        project_id="prj-aaa",
        title="Draft outline",
        body="Use 5 sections",
        created_by="user-1",
    )
    assert t["id"].startswith("tsk-")
    assert t["status"] == "open"
    assert t["title"] == "Draft outline"
    assert t["claimed_by"] is None
    assert t["parent_task_id"] is None

    again = await store.get_task(t["id"])
    assert again == t


@pytest.mark.asyncio
async def test_create_subtask(store):
    parent = await store.create_task(project_id="prj-aaa", title="P", created_by="u")
    child = await store.create_task(
        project_id="prj-aaa",
        title="C",
        created_by="u",
        parent_task_id=parent["id"],
    )
    assert child["parent_task_id"] == parent["id"]


@pytest.mark.asyncio
async def test_list_tasks_filter_by_status(store):
    a = await store.create_task(project_id="p", title="A", created_by="u")
    b = await store.create_task(project_id="p", title="B", created_by="u")
    await store.close_task(b["id"], closed_by="u")

    open_tasks = await store.list_tasks(project_id="p", status="open")
    closed_tasks = await store.list_tasks(project_id="p", status="closed")
    assert [t["id"] for t in open_tasks] == [a["id"]]
    assert [t["id"] for t in closed_tasks] == [b["id"]]


@pytest.mark.asyncio
async def test_atomic_claim_only_one_winner(store):
    t = await store.create_task(project_id="p", title="A", created_by="u")
    first = await store.claim_task(t["id"], claimer_id="agent-1")
    second = await store.claim_task(t["id"], claimer_id="agent-2")
    assert first is True
    assert second is False
    again = await store.get_task(t["id"])
    assert again["claimed_by"] == "agent-1"
    assert again["status"] == "claimed"


@pytest.mark.asyncio
async def test_release_task(store):
    t = await store.create_task(project_id="p", title="A", created_by="u")
    await store.claim_task(t["id"], claimer_id="agent-1")
    await store.release_task(t["id"], releaser_id="agent-1")
    again = await store.get_task(t["id"])
    assert again["claimed_by"] is None
    assert again["status"] == "open"


@pytest.mark.asyncio
async def test_release_only_by_claimer(store):
    t = await store.create_task(project_id="p", title="A", created_by="u")
    await store.claim_task(t["id"], claimer_id="agent-1")
    ok = await store.release_task(t["id"], releaser_id="agent-2")
    assert ok is False
    again = await store.get_task(t["id"])
    assert again["claimed_by"] == "agent-1"


@pytest.mark.asyncio
async def test_close_task_records_metadata(store):
    t = await store.create_task(project_id="p", title="A", created_by="u")
    await store.close_task(t["id"], closed_by="agent-1", reason="done")
    again = await store.get_task(t["id"])
    assert again["status"] == "closed"
    assert again["closed_by"] == "agent-1"
    assert again["close_reason"] == "done"
    assert again["closed_at"] is not None
