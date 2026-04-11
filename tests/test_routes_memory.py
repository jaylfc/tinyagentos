"""Memory route tests.

Every path now goes through ``qmd serve``'s HTTP endpoints (``GET /search``,
``GET /browse``, ``GET /collections``, ``POST /vsearch``). These tests
stub ``app.state.http_client.get`` / ``post`` so we can assert the routes
shape requests and unpack responses correctly without needing a live
``qmd serve`` process.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _stub_http(client_with_qmd, responses: dict[str, dict]):
    """Install an AsyncMock http_client onto the app that returns the
    canned JSON body for matching path suffixes. Keys are path suffixes
    like ``/browse`` or ``/search``; values are the JSON body the
    endpoint should echo."""
    app = client_with_qmd._transport.app

    def _response_for(path_suffix: str) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=responses[path_suffix])
        return resp

    async def _get(url: str, *, params=None, timeout=None, **kw):
        for suffix, body in responses.items():
            if url.endswith(suffix):
                return _response_for(suffix)
        raise AssertionError(f"unexpected GET {url}")

    async def _post(url: str, *, json=None, timeout=None, **kw):
        for suffix, body in responses.items():
            if url.endswith(suffix):
                return _response_for(suffix)
        raise AssertionError(f"unexpected POST {url}")

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=_get)
    mock_client.post = AsyncMock(side_effect=_post)
    # conftest's teardown awaits http_client.aclose() — give it an
    # awaitable even though there's nothing to close.
    mock_client.aclose = AsyncMock(return_value=None)
    app.state.http_client = mock_client


@pytest.mark.asyncio
class TestMemoryPage:
    async def test_memory_page_returns_html(self, client_with_qmd):
        resp = await client_with_qmd.get("/memory")
        assert resp.status_code == 200
        assert "Memory" in resp.text

    async def test_browse_returns_chunks(self, client_with_qmd):
        _stub_http(client_with_qmd, {
            "/browse": {"chunks": [{"hash": "a"}, {"hash": "b"}, {"hash": "c"}], "total": 3},
        })
        resp = await client_with_qmd.get("/api/memory/browse?agent=test-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["chunks"]) == 3

    async def test_browse_by_collection(self, client_with_qmd):
        _stub_http(client_with_qmd, {
            "/browse": {"chunks": [{"hash": "a"}, {"hash": "b"}], "total": 2},
        })
        resp = await client_with_qmd.get(
            "/api/memory/browse?agent=test-agent&collection=transcripts",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["chunks"]) == 2

    async def test_keyword_search(self, client_with_qmd):
        _stub_http(client_with_qmd, {
            "/search": {"results": [{"hash": "abc", "body": "Q2 roadmap notes"}], "total": 1},
        })
        resp = await client_with_qmd.post("/api/memory/search", json={
            "query": "roadmap", "mode": "keyword", "agent": "test-agent",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) >= 1

    async def test_collections_endpoint(self, client_with_qmd):
        _stub_http(client_with_qmd, {
            "/collections": [{"name": "transcripts"}, {"name": "notes"}],
        })
        resp = await client_with_qmd.get("/api/memory/collections/test-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
