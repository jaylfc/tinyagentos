from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from tinyagentos.agent_db import find_agent, get_agent_summaries
from tinyagentos.config import save_config_locked, validate_agent_name

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
    return templates.TemplateResponse(request, "agents.html", {
        "active_page": "agents", "agents": get_agent_summaries(config),
    })


@router.get("/api/agents")
async def list_agents(request: Request):
    return request.app.state.config.agents


@router.get("/api/agents/containers")
async def list_agent_containers(request: Request):
    """List live LXC container status for all agent containers."""
    from tinyagentos.containers import list_containers
    containers = await list_containers(prefix="agent-")
    return [
        {
            "name": c.name,
            "agent_name": c.name.removeprefix("agent-"),
            "status": c.status,
            "ip": c.ip,
            "memory_mb": c.memory_mb,
            "cpu_cores": c.cpu_cores,
        }
        for c in containers
    ]


@router.get("/api/agents/{name}")
async def get_agent_endpoint(request: Request, name: str):
    config = request.app.state.config
    agent = find_agent(config, name)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)
    return agent


@router.post("/api/agents")
async def add_agent(request: Request, body: AgentCreate):
    config = request.app.state.config
    name_error = validate_agent_name(body.name)
    if name_error:
        return JSONResponse({"error": name_error}, status_code=400)
    if find_agent(config, body.name):
        return JSONResponse({"error": f"Agent '{body.name}' already exists"}, status_code=409)
    config.agents.append(body.model_dump())
    await save_config_locked(config, config.config_path)
    return {"status": "created", "name": body.name}


@router.put("/api/agents/{name}")
async def update_agent(request: Request, name: str, body: AgentUpdate):
    config = request.app.state.config
    agent = find_agent(config, name)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)
    if body.host is not None:
        agent["host"] = body.host
    if body.qmd_index is not None:
        agent["qmd_index"] = body.qmd_index
    if body.color is not None:
        agent["color"] = body.color
    await save_config_locked(config, config.config_path)
    return {"status": "updated", "name": name}


@router.delete("/api/agents/{name}")
async def delete_agent(request: Request, name: str):
    config = request.app.state.config
    config.agents = [a for a in config.agents if a["name"] != name]
    await save_config_locked(config, config.config_path)
    return {"status": "deleted", "name": name}


class DeployAgentRequest(BaseModel):
    name: str
    framework: str = "none"
    model: str | None = None
    color: str = "#888888"
    memory_limit: str = "2GB"
    cpu_limit: int = 2


@router.post("/api/agents/deploy")
async def deploy_agent_endpoint(request: Request, body: DeployAgentRequest):
    config = request.app.state.config
    name_error = validate_agent_name(body.name)
    if name_error:
        return JSONResponse({"error": name_error}, status_code=400)
    # Validate framework against catalog instead of hardcoded list
    if body.framework != "none":
        registry = request.app.state.registry
        known = {a.id for a in registry.list_available(type_filter="agent-framework")}
        if body.framework not in known:
            return JSONResponse({"error": f"Unknown framework '{body.framework}'. Available: {sorted(known)}"}, status_code=400)
    if find_agent(config, body.name):
        return JSONResponse({"error": f"Agent '{body.name}' already exists"}, status_code=409)

    from tinyagentos.deployer import deploy_agent, DeployRequest
    rkllama_url = "http://localhost:8080"
    for b in config.backends:
        if b.get("type") == "rkllama":
            rkllama_url = b["url"]
            break

    result = await deploy_agent(DeployRequest(
        name=body.name,
        framework=body.framework,
        model=body.model,
        color=body.color,
        memory_limit=body.memory_limit,
        cpu_limit=body.cpu_limit,
        rkllama_url=rkllama_url,
    ))

    if result["success"]:
        config.agents.append({
            "name": body.name,
            "host": result.get("ip", ""),
            "qmd_url": result.get("qmd_url", ""),
            "color": body.color,
        })
        await save_config_locked(config, config.config_path)

    return result


@router.post("/api/agents/{name}/start")
async def start_agent(request: Request, name: str):
    from tinyagentos.containers import start_container
    return await start_container(f"agent-{name}")


@router.post("/api/agents/{name}/stop")
async def stop_agent(request: Request, name: str):
    from tinyagentos.containers import stop_container
    return await stop_container(f"agent-{name}")


@router.post("/api/agents/{name}/restart")
async def restart_agent(request: Request, name: str):
    from tinyagentos.containers import restart_container
    return await restart_container(f"agent-{name}")


@router.get("/api/agents/{name}/logs")
async def agent_logs(request: Request, name: str, lines: int = 100):
    from tinyagentos.containers import get_container_logs
    logs = await get_container_logs(f"agent-{name}", lines=lines)
    return {"name": name, "logs": logs}


@router.delete("/api/agents/{name}/destroy")
async def destroy_agent(request: Request, name: str):
    config = request.app.state.config
    from tinyagentos.deployer import undeploy_agent
    result = await undeploy_agent(name)
    if result["success"]:
        config.agents = [a for a in config.agents if a["name"] != name]
        await save_config_locked(config, config.config_path)
    return result
