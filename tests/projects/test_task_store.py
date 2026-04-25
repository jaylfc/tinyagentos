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
