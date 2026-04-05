from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from tinyagentos.agent_db import get_agent_db
from tinyagentos.config import save_config

router = APIRouter()

class AgentCreate(BaseModel):
    name: str
    host: str
    qmd_index: str
    color: str = "#888888"

class AgentUpdate(BaseModel):
    host: str | None = None
    qmd_index: str | None = None
    color: str | None = None

@router.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request):
    config = request.app.state.config
    templates = request.app.state.templates
    agents = []
    for agent in config.agents:
        db = get_agent_db(agent)
        vectors = db.vector_count() if db else 0
        status = "ok" if db else "error"
        agents.append({**agent, "vectors": vectors, "status": status})
    return templates.TemplateResponse("agents.html", {
        "request": request, "active_page": "agents", "agents": agents,
    })

@router.get("/api/agents")
async def list_agents(request: Request):
    return request.app.state.config.agents

@router.get("/api/agents/{name}")
async def get_agent(request: Request, name: str):
    config = request.app.state.config
    agent = next((a for a in config.agents if a["name"] == name), None)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)
    return agent

@router.post("/api/agents")
async def add_agent(request: Request, body: AgentCreate):
    config = request.app.state.config
    if any(a["name"] == body.name for a in config.agents):
        return JSONResponse({"error": f"Agent '{body.name}' already exists"}, status_code=409)
    config.agents.append(body.model_dump())
    save_config(config, config.config_path)
    return {"status": "created", "name": body.name}

@router.put("/api/agents/{name}")
async def update_agent(request: Request, name: str, body: AgentUpdate):
    config = request.app.state.config
    agent = next((a for a in config.agents if a["name"] == name), None)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)
    if body.host is not None:
        agent["host"] = body.host
    if body.qmd_index is not None:
        agent["qmd_index"] = body.qmd_index
    if body.color is not None:
        agent["color"] = body.color
    save_config(config, config.config_path)
    return {"status": "updated", "name": name}

@router.delete("/api/agents/{name}")
async def delete_agent(request: Request, name: str):
    config = request.app.state.config
    config.agents = [a for a in config.agents if a["name"] != name]
    save_config(config, config.config_path)
    return {"status": "deleted", "name": name}
