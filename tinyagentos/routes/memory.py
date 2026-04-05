from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from tinyagentos.qmd_db import QmdDatabase

router = APIRouter()

QMD_CACHE_DIR = Path.home() / ".cache" / "qmd"


class SearchRequest(BaseModel):
    query: str
    mode: str = "keyword"
    agent: Optional[str] = None
    collection: Optional[str] = None
    limit: int = 20


def _get_agent_db(config, agent_name: str) -> tuple[QmdDatabase | None, dict | None]:
    """Look up agent in config, build db path from qmd_index, return (db, agent_dict)."""
    agent_dict = None
    for a in config.agents:
        if a["name"] == agent_name:
            agent_dict = a
            break
    if agent_dict is None:
        return None, None
    index_name = agent_dict.get("qmd_index", "index")
    db_path = QMD_CACHE_DIR / f"{index_name}.sqlite"
    try:
        db = QmdDatabase(db_path)
    except FileNotFoundError:
        return None, agent_dict
    return db, agent_dict


@router.get("/memory", response_class=HTMLResponse)
async def memory_page(request: Request):
    config = request.app.state.config
    templates = request.app.state.templates
    agents = []
    for agent in config.agents:
        index_name = agent.get("qmd_index", "index")
        db_path = QMD_CACHE_DIR / f"{index_name}.sqlite"
        try:
            db = QmdDatabase(db_path)
            vectors = db.vector_count()
        except FileNotFoundError:
            vectors = 0
        agents.append({
            "name": agent["name"],
            "color": agent.get("color", "#888"),
            "vectors": vectors,
        })
    return templates.TemplateResponse("memory.html", {
        "request": request,
        "active_page": "memory",
        "agents": agents,
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
    db, agent_dict = _get_agent_db(config, agent)
    if db is None:
        return JSONResponse({"chunks": [], "error": f"Agent '{agent}' not found or database missing"})
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
        db, agent_dict = _get_agent_db(config, body.agent)
        if db is None:
            return JSONResponse({"results": [], "error": f"Agent '{body.agent}' not found or database missing"})
        try:
            results = db.keyword_search(body.query, collection=body.collection, limit=body.limit)
            return {"results": results}
        except Exception as e:
            return JSONResponse({"results": [], "error": str(e)})

    # Search across all agents
    all_results = []
    for agent in config.agents:
        db, _ = _get_agent_db(config, agent["name"])
        if db is None:
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
    db, agent_dict = _get_agent_db(config, agent_name)
    if db is None:
        return JSONResponse([], status_code=200)
    return db.collections()


@router.delete("/api/memory/chunk/{content_hash}")
async def memory_delete_chunk(request: Request, content_hash: str, agent: str):
    config = request.app.state.config
    db, agent_dict = _get_agent_db(config, agent)
    if db is None:
        return JSONResponse({"status": "error", "message": "Agent not found or database missing"}, status_code=404)
    try:
        db.delete_chunk(content_hash)
        return {"status": "deleted"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
