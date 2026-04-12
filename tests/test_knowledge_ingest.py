from __future__ import annotations
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from tinyagentos.knowledge_store import KnowledgeStore
from tinyagentos.knowledge_ingest import IngestPipeline, resolve_source_type


# --- URL resolution ---

def test_resolve_reddit():
    assert resolve_source_type("https://reddit.com/r/LocalLLaMA/comments/abc") == "reddit"
    assert resolve_source_type("https://www.reddit.com/r/Python/comments/xyz/") == "reddit"


def test_resolve_youtube():
    assert resolve_source_type("https://www.youtube.com/watch?v=abc123") == "youtube"
    assert resolve_source_type("https://youtu.be/abc123") == "youtube"


def test_resolve_x():
    assert resolve_source_type("https://x.com/user/status/123") == "x"
    assert resolve_source_type("https://twitter.com/user/status/456") == "x"


def test_resolve_github():
    assert resolve_source_type("https://github.com/some/repo") == "github"
    assert resolve_source_type("https://github.com/org/repo/issues/1") == "github"


def test_resolve_article_fallback():
    assert resolve_source_type("https://news.ycombinator.com/item?id=123") == "article"
    assert resolve_source_type("https://blog.example.com/some-post") == "article"


# --- IngestPipeline ---

@pytest_asyncio.fixture
async def store(tmp_path):
    s = KnowledgeStore(tmp_path / "knowledge.db", media_dir=tmp_path / "media")
    await s.init()
    yield s
    await s.close()


@pytest.fixture
def mock_http():
    client = AsyncMock()
    # Default: return minimal HTML for article fetch
    response = MagicMock()
    response.status_code = 200
    response.text = "<html><body><article><p>This is the main article content with enough text to pass the quality threshold.</p></article></body></html>"
    response.raise_for_status = MagicMock()
    client.get = AsyncMock(return_value=response)
    return client


@pytest_asyncio.fixture
async def pipeline(store, mock_http):
    notif = AsyncMock()
    notif.emit_event = AsyncMock()
    cat_engine = AsyncMock()
    cat_engine.categorise = AsyncMock(return_value=["Tech"])
    p = IngestPipeline(
        store=store,
        http_client=mock_http,
        notifications=notif,
        category_engine=cat_engine,
        qmd_base_url="",  # QMD disabled for unit tests
        llm_base_url="",  # LLM disabled for unit tests
    )
    return p


@pytest.mark.asyncio
async def test_ingest_creates_pending_item(pipeline, store):
    item_id = await pipeline.submit(
        url="https://example.com/article",
        title="",
        text="",
        categories=[],
        source="test",
    )
    assert item_id
    item = await store.get_item(item_id)
    assert item is not None
    assert item["status"] in ("pending", "processing", "ready", "error")
    assert item["source_url"] == "https://example.com/article"


@pytest.mark.asyncio
async def test_ingest_article_sets_ready(pipeline, store):
    item_id = await pipeline.submit(
        url="https://example.com/article",
        title="",
        text="",
        categories=[],
        source="test",
    )
    # Run the pipeline inline (not background) for testing
    await pipeline.run(item_id)
    item = await store.get_item(item_id)
    assert item["status"] == "ready"
    assert item["source_type"] == "article"


@pytest.mark.asyncio
async def test_ingest_with_text_override(pipeline, store):
    """When text is provided directly, skip HTTP download."""
    item_id = await pipeline.submit(
        url="https://example.com/article",
        title="My Title",
        text="Pre-provided content that is long enough to pass quality checks.",
        categories=["Tech"],
        source="share-sheet",
    )
    await pipeline.run(item_id)
    item = await store.get_item(item_id)
    assert item["status"] == "ready"
    assert "Pre-provided content" in item["content"]


@pytest.mark.asyncio
async def test_ingest_notifies_on_ready(pipeline, store):
    item_id = await pipeline.submit(
        url="https://example.com/article",
        title="",
        text="",
        categories=[],
        source="test",
    )
    await pipeline.run(item_id)
    pipeline._notifications.emit_event.assert_awaited()


@pytest.mark.asyncio
async def test_ingest_sets_error_on_failure(pipeline, store):
    pipeline._http_client.get = AsyncMock(side_effect=Exception("network failure"))
    item_id = await pipeline.submit(
        url="https://example.com/failing",
        title="",
        text="",
        categories=[],
        source="test",
    )
    await pipeline.run(item_id)
    item = await store.get_item(item_id)
    assert item["status"] == "error"
