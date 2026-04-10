import pytest
import pytest_asyncio
from tinyagentos.user_memory import UserMemoryStore


@pytest_asyncio.fixture
async def store(tmp_path):
    s = UserMemoryStore(tmp_path / "user_mem.db")
    await s.init()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_save_and_search(store):
    h = await store.save_chunk("user", "This is a test snippet about python", "Python Note", "snippets")
    assert h
    results = await store.search("user", "python")
    assert len(results) == 1
    assert results[0]["content"] == "This is a test snippet about python"


@pytest.mark.asyncio
async def test_browse_by_collection(store):
    await store.save_chunk("user", "Note one", "Title 1", "notes")
    await store.save_chunk("user", "Snippet one", "Title 2", "snippets")
    notes = await store.browse("user", collection="notes")
    assert len(notes) == 1
    assert notes[0]["collection"] == "notes"


@pytest.mark.asyncio
async def test_stats(store):
    await store.save_chunk("user", "a", "1", "notes")
    await store.save_chunk("user", "b", "2", "notes")
    await store.save_chunk("user", "c", "3", "snippets")
    stats = await store.get_stats("user")
    assert stats["total"] == 3
    assert stats["collections"]["notes"] == 2


@pytest.mark.asyncio
async def test_delete(store):
    h = await store.save_chunk("user", "delete me", "gone", "snippets")
    assert await store.delete_chunk("user", h) is True
    results = await store.search("user", "delete")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_settings(store):
    settings = await store.get_settings("user")
    assert settings["capture_notes"] is True
    await store.update_settings("user", {"capture_notes": False})
    settings = await store.get_settings("user")
    assert settings["capture_notes"] is False
