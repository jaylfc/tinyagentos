from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from tinyagentos.agent_db import find_agent, get_agent_db, get_agent_summaries

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
    agent: str,
    collection: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    config = request.app.state.config
    agent_dict = find_agent(config, agent)
    if not agent_dict:
        return JSONResponse({"chunks": [], "error": f"Agent '{agent}' not found"})
    db = get_agent_db(agent_dict)
    if not db:
        return JSONResponse({"chunks": [], "error": f"Database missing for agent '{agent}'"})
    try:
        chunks = db.browse(collection=collection, limit=limit, offset=offset)
        return {"chunks": chunks}
    except Exception as e:
        return JSONResponse({"chunks": [], "error": str(e)})


@router.post("/api/memory/search")
async def memory_search(request: Request, body: SearchRequest):
    config = request.app.state.config

    if body.mode == "semantic":
        return JSONResponse({"results": [], "error": "Semantic search not yet implemented"})

    if body.agent:
        agent_dict = find_agent(config, body.agent)
        if not agent_dict:
            return JSONResponse({"results": [], "error": f"Agent '{body.agent}' not found"})
        db = get_agent_db(agent_dict)
        if not db:
            return JSONResponse({"results": [], "error": f"Database missing for agent '{body.agent}'"})
        try:
            results = db.keyword_search(body.query, collection=body.collection, limit=body.limit)
            return {"results": results}
        except Exception as e:
            return JSONResponse({"results": [], "error": str(e)})

    # Search across all agents
    all_results = []
    for agent in config.agents:
        db = get_agent_db(agent)
        if not db:
            continue
        try:
            results = db.keyword_search(body.query, collection=body.collection, limit=body.limit)
            for r in results:
                r["agent"] = agent["name"]
            all_results.extend(results)
        except Exception:
            continue
    return {"results": all_results}


@router.get("/api/memory/collections/{agent_name}")
async def memory_collections(request: Request, agent_name: str):
    config = request.app.state.config
    agent_dict = find_agent(config, agent_name)
    if not agent_dict:
        return JSONResponse([], status_code=200)
    db = get_agent_db(agent_dict)
    if not db:
        return JSONResponse([], status_code=200)
    return db.collections()


@router.delete("/api/memory/chunk/{content_hash}")
async def memory_delete_chunk(request: Request, content_hash: str, agent: str):
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
