import pytest
import pytest_asyncio
from tinyagentos.browsing_history import BrowsingHistoryStore


@pytest_asyncio.fixture
async def store(tmp_path):
    s = BrowsingHistoryStore(db_path=tmp_path / "history.db")
    await s.init()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_record_and_list(store):
    await store.record("https://reddit.com/r/test/1", "reddit", title="Test Post", author="user1")
    await store.record("https://reddit.com/r/test/2", "reddit", title="Second Post", author="user2")
    items = await store.list_recent(source_type="reddit")
    assert len(items) == 2
    assert items[0]["title"] == "Second Post"  # newest first


@pytest.mark.asyncio
async def test_upsert_updates_viewed_at(store):
    await store.record("https://x.com/tweet/1", "x", title="Old Title")
    await store.record("https://x.com/tweet/1", "x", title="Updated Title")
    items = await store.list_recent(source_type="x")
    assert len(items) == 1
    assert items[0]["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_filter_by_source_type(store):
    await store.record("https://reddit.com/1", "reddit", title="Reddit")
    await store.record("https://x.com/1", "x", title="Tweet")
    reddit = await store.list_recent(source_type="reddit")
    x = await store.list_recent(source_type="x")
    assert len(reddit) == 1
    assert len(x) == 1
    all_items = await store.list_recent()
    assert len(all_items) == 2


@pytest.mark.asyncio
async def test_clear(store):
    await store.record("https://reddit.com/1", "reddit", title="R1")
    await store.record("https://x.com/1", "x", title="X1")
    deleted = await store.clear(source_type="reddit")
    assert deleted == 1
    remaining = await store.list_recent()
    assert len(remaining) == 1
    assert remaining[0]["source_type"] == "x"


@pytest.mark.asyncio
async def test_clear_all(store):
    await store.record("https://reddit.com/1", "reddit", title="R1")
    await store.record("https://x.com/1", "x", title="X1")
    deleted = await store.clear()
    assert deleted == 2
    assert await store.list_recent() == []


@pytest.mark.asyncio
async def test_preview_truncated(store):
    long_text = "x" * 500
    await store.record("https://test.com/1", "reddit", preview=long_text)
    items = await store.list_recent()
    assert len(items[0]["preview"]) <= 200


@pytest.mark.asyncio
async def test_limit(store):
    for i in range(10):
        await store.record(f"https://reddit.com/{i}", "reddit", title=f"Post {i}")
    items = await store.list_recent(limit=5)
    assert len(items) == 5
