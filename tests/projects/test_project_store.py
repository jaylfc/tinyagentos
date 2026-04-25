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
