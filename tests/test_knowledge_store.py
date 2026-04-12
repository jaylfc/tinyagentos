from __future__ import annotations
import json
import time
import pytest
import pytest_asyncio
from pathlib import Path
from tinyagentos.knowledge_store import KnowledgeStore


@pytest_asyncio.fixture
async def store(tmp_path):
    s = KnowledgeStore(tmp_path / "knowledge.db", media_dir=tmp_path / "knowledge-media")
    await s.init()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_add_and_get_item(store):
    item_id = await store.add_item(
        source_type="article",
        source_url="https://example.com/post",
        title="Test Article",
        author="tester",
        content="Full text of the article goes here.",
        summary="A brief summary.",
        categories=["Tech"],
        tags=["python"],
        metadata={"word_count": 8},
    )
    assert item_id  # non-empty string
    item = await store.get_item(item_id)
    assert item is not None
    assert item["title"] == "Test Article"
    assert item["source_type"] == "article"
    assert item["status"] == "pending"
    assert item["categories"] == ["Tech"]
    assert item["tags"] == ["python"]


@pytest.mark.asyncio
async def test_get_item_not_found(store):
    item = await store.get_item("nonexistent-id")
    assert item is None


@pytest.mark.asyncio
async def test_update_status(store):
    item_id = await store.add_item(
        source_type="article",
        source_url="https://example.com/post2",
        title="Another Article",
        author="tester",
        content="Content.",
        summary="Summary.",
        categories=[],
        tags=[],
        metadata={},
    )
    await store.update_status(item_id, "ready")
    item = await store.get_item(item_id)
    assert item["status"] == "ready"


@pytest.mark.asyncio
async def test_list_items(store):
    for i in range(3):
        await store.add_item(
            source_type="article",
            source_url=f"https://example.com/{i}",
            title=f"Article {i}",
            author="tester",
            content="Content.",
            summary="Summary.",
            categories=["Tech"],
            tags=[],
            metadata={},
        )
    items = await store.list_items(limit=10)
    assert len(items) == 3


@pytest.mark.asyncio
async def test_delete_item(store):
    item_id = await store.add_item(
        source_type="article",
        source_url="https://example.com/del",
        title="To Delete",
        author="tester",
        content="Content.",
        summary="Summary.",
        categories=[],
        tags=[],
        metadata={},
    )
    deleted = await store.delete_item(item_id)
    assert deleted is True
    assert await store.get_item(item_id) is None
