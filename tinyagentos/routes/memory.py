"""Memory routes — keyword and semantic search over per-agent stores.

Every memory operation goes through the single host ``qmd.service``
systemd unit on :7832. That process exposes ``/search`` and ``/vsearch``
in addition to the model primitives (``/embed``, ``/rerank``,
``/expand``), so TinyAgentOS never needs to open a SQLite DB from
Python or know which embedder / dimension is in use.

Previous revisions fell back to opening per-agent SQLite files via
``agent_db.get_agent_db``, which required the sqlite-vec extension and
was the source of the dim-mismatch and extension-loading pain. The new
flow is pure HTTP: embed, rerank, and search all land on one address.
See ``docs/design/framework-agnostic-runtime.md``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from tinyagentos.agent_db import get_agent_summaries

logger = logging.getLogger(__name__)

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    mode: str = "keyword"
    agent: str | None = None
    collection: str | None = None
    limit: int = 20


@router.get("/memory", response_class=HTMLResponse)
async def memory_page(request: Request):
    config = request.app.state.config
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "memory.html", {
        "active_page": "memory",
        "agents": get_agent_summaries(config),
    })


@router.get("/api/memory/browse")
async def memory_browse(
    request: Request,
    agent: str | None = None,
    collection: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    """Browse memory chunks via qmd serve GET /browse."""
    http_client = request.app.state.http_client
    params: dict = {"limit": limit, "offset": offset}
    if collection:
        params["collection"] = collection
    try:
        resp = await http_client.get(f"{_qmd_base(request)}/browse", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        chunks = data.get("chunks", [])
        if agent:
            for c in chunks:
                c["agent"] = agent
        return {"chunks": chunks}
    except Exception as e:
        logger.warning("qmd /browse failed: %s", e)
        return JSONResponse({"chunks": [], "error": str(e)}, status_code=502)


def _keyword_search_agent(agent_dict: dict, query: str,
                          collection: str | None = None, limit: int = 20) -> list[dict]:
    db = get_agent_db(agent_dict)
    if not db:
        return []
    return db.keyword_search(query, collection=collection, limit=limit)


def _qmd_base(request: Request) -> str:
    """URL of the shared host qmd serve process."""
    return request.app.state.qmd_client.base_url


async def _qmd_search(request: Request, query: str,
                      collection: str | None, limit: int) -> list[dict]:
    """Keyword (BM25) search via qmd serve GET /search."""
    http_client = request.app.state.http_client
    params: dict = {"q": query, "limit": limit}
    if collection:
        params["collection"] = collection
    resp = await http_client.get(f"{_qmd_base(request)}/search", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("results", [])


async def _qmd_vsearch(request: Request, query: str,
                       collection: str | None, limit: int) -> list[dict]:
    """Semantic (vector) search via qmd serve /vsearch. The query is
    embedded inside the qmd serve process using whichever backend that
    process is configured with (rkllama on NPU in our deployment)."""
    http_client = request.app.state.http_client
    payload: dict = {"query": query, "limit": limit}
    if collection:
        payload["collection"] = collection
    resp = await http_client.post(f"{_qmd_base(request)}/vsearch", json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data.get("results", [])


@router.post("/api/memory/search")
async def memory_search(request: Request, body: SearchRequest):
    """Search agent memory using keyword or semantic search."""
    config = request.app.state.config

    search_fn = _qmd_vsearch if body.mode == "semantic" else _qmd_search

    try:
        results = await search_fn(request, body.query, body.collection, body.limit)
    except Exception as exc:
        logger.warning("qmd %s failed: %s", body.mode, exc)
        return JSONResponse({"results": [], "error": str(exc)}, status_code=502)

    # Optional per-agent tagging for UI display. Filtering by agent is
    # not yet supported at the qmd serve level — every agent shares the
    # same index until per-agent dbPath routing is wired through.
    if body.agent:
        for r in results:
            r["agent"] = body.agent
    return {"results": results}


@router.get("/api/memory/collections/{agent_name}")
async def memory_collections(request: Request, agent_name: str):
    """List memory collections via qmd serve GET /collections.

    The agent_name path parameter is accepted for API compatibility but
    currently ignored — the shared qmd.service points at a single
    index. Per-agent collection filtering is a follow-up once the
    upstream qmd serve grows per-request dbPath routing.
    """
    _ = agent_name
    http_client = request.app.state.http_client
    try:
        resp = await http_client.get(f"{_qmd_base(request)}/collections", timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("qmd /collections failed: %s", e)
        return JSONResponse([], status_code=200)


@router.delete("/api/memory/chunk/{content_hash}")
async def memory_delete_chunk(request: Request, content_hash: str, agent: str | None = None):
    """Delete a specific memory chunk by content hash.

    qmd serve does not yet expose a deletion endpoint — this route
    returns 501 until upstream qmd-server grows one. Tracking under
    the framework-agnostic runtime follow-ups.
    """
    _ = content_hash, agent
    return JSONResponse(
        {
            "status": "error",
            "message": "Chunk deletion is not yet exposed by qmd serve — "
                       "pending an upstream endpoint.",
        },
        status_code=501,
    )
