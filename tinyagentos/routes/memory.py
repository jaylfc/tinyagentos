from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from tinyagentos.agent_db import find_agent, get_agent_db, get_agent_summaries

logger = logging.getLogger(__name__)

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    mode: str = "keyword"
    agent: str | None = None
    collection: str | None = None
    limit: int = 20


async def _search_via_http(http_client, qmd_url: str, query: str,
                           collection: str | None = None, limit: int = 20) -> list[dict]:
    """Search an agent's qmd serve instance over HTTP."""
    params: dict = {"q": query, "limit": limit}
    if collection:
        params["collection"] = collection
    url = qmd_url.rstrip("/") + "/search"
    resp = await http_client.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    # qmd serve /search returns {"results": [...]} or a list directly
    if isinstance(data, list):
        return data
    return data.get("results", data.get("chunks", []))


async def _browse_via_http(http_client, qmd_url: str,
                           collection: str | None = None,
                           limit: int = 20, offset: int = 0) -> list[dict]:
    """Browse an agent's qmd serve instance over HTTP."""
    params: dict = {"limit": limit, "offset": offset}
    if collection:
        params["collection"] = collection
    url = qmd_url.rstrip("/") + "/browse"
    resp = await http_client.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data
    return data.get("chunks", data.get("results", []))


async def _collections_via_http(http_client, qmd_url: str) -> list:
    """Get collections from an agent's qmd serve instance over HTTP."""
    url = qmd_url.rstrip("/") + "/collections"
    resp = await http_client.get(url)
    resp.raise_for_status()
    return resp.json()


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
    agent: str,
    collection: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    """Browse agent memory chunks, paginated, most recent first."""
    config = request.app.state.config
    agent_dict = find_agent(config, agent)
    if not agent_dict:
        return JSONResponse({"chunks": [], "error": f"Agent '{agent}' not found"})

    # Try HTTP via qmd_url first
    qmd_url = agent_dict.get("qmd_url")
    if qmd_url:
        http_client = request.app.state.http_client
        try:
            chunks = await _browse_via_http(http_client, qmd_url,
                                            collection=collection, limit=limit, offset=offset)
            return {"chunks": chunks}
        except Exception as e:
            logger.warning("qmd_url browse failed for %s (%s), falling back to local DB: %s",
                           agent, qmd_url, e)

    # Fall back to local SQLite via qmd_index
    db = get_agent_db(agent_dict)
    if not db:
        return JSONResponse({"chunks": [], "error": f"Database missing for agent '{agent}'"})
    try:
        chunks = db.browse(collection=collection, limit=limit, offset=offset)
        return {"chunks": chunks}
    except Exception as e:
        return JSONResponse({"chunks": [], "error": str(e)})


async def _search_single_agent(request: Request, agent_dict: dict, query: str,
                               collection: str | None = None, limit: int = 20) -> list[dict]:
    """Search a single agent, trying HTTP first then local DB."""
    qmd_url = agent_dict.get("qmd_url")
    if qmd_url:
        http_client = request.app.state.http_client
        try:
            return await _search_via_http(http_client, qmd_url, query,
                                          collection=collection, limit=limit)
        except Exception as e:
            logger.warning("qmd_url search failed for %s (%s), falling back to local DB: %s",
                           agent_dict.get("name"), qmd_url, e)

    db = get_agent_db(agent_dict)
    if not db:
        return []
    return db.keyword_search(query, collection=collection, limit=limit)


@router.post("/api/memory/search")
async def memory_search(request: Request, body: SearchRequest):
    """Search agent memory using keyword or semantic search."""
    config = request.app.state.config

    if body.mode == "semantic":
        # Semantic uses the same qmd /search endpoint for now (FTS5 keyword)
        # until qmd serve adds a proper vector search endpoint
        if body.agent:
            agent_dict = find_agent(config, body.agent)
            if not agent_dict:
                return JSONResponse({"results": [], "error": f"Agent '{body.agent}' not found"})
            qmd_url = agent_dict.get("qmd_url")
            if qmd_url:
                http_client = request.app.state.http_client
                try:
                    results = await _search_via_http(http_client, qmd_url, body.query,
                                                     collection=body.collection, limit=body.limit)
                    return {"results": results, "note": "Using keyword search via qmd serve (vector search pending)"}
                except Exception:
                    pass
        return JSONResponse({"results": [], "error": "Semantic search requires agent with qmd_url"})

    if body.agent:
        agent_dict = find_agent(config, body.agent)
        if not agent_dict:
            return JSONResponse({"results": [], "error": f"Agent '{body.agent}' not found"})
        try:
            results = await _search_single_agent(request, agent_dict, body.query,
                                                 collection=body.collection, limit=body.limit)
            return {"results": results}
        except Exception as e:
            return JSONResponse({"results": [], "error": str(e)})

    # Search across all agents
    all_results = []
    for agent in config.agents:
        try:
            results = await _search_single_agent(request, agent, body.query,
                                                 collection=body.collection, limit=body.limit)
            for r in results:
                r["agent"] = agent["name"]
            all_results.extend(results)
        except Exception:
            continue
    return {"results": all_results}


@router.get("/api/memory/collections/{agent_name}")
async def memory_collections(request: Request, agent_name: str):
    """List memory collections for an agent."""
    config = request.app.state.config
    agent_dict = find_agent(config, agent_name)
    if not agent_dict:
        return JSONResponse([], status_code=200)

    # Try HTTP via qmd_url first
    qmd_url = agent_dict.get("qmd_url")
    if qmd_url:
        http_client = request.app.state.http_client
        try:
            return await _collections_via_http(http_client, qmd_url)
        except Exception as e:
            logger.warning("qmd_url collections failed for %s (%s), falling back to local DB: %s",
                           agent_name, qmd_url, e)

    db = get_agent_db(agent_dict)
    if not db:
        return JSONResponse([], status_code=200)
    return db.collections()


@router.delete("/api/memory/chunk/{content_hash}")
async def memory_delete_chunk(request: Request, content_hash: str, agent: str):
    """Delete a specific memory chunk by content hash."""
    config = request.app.state.config
    agent_dict = find_agent(config, agent)
    if not agent_dict:
        return JSONResponse({"status": "error", "message": "Agent not found"}, status_code=404)
    db = get_agent_db(agent_dict)
    if not db:
        return JSONResponse({"status": "error", "message": "Database missing"}, status_code=404)
    try:
        db.delete_chunk(content_hash)
        return {"status": "deleted"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
