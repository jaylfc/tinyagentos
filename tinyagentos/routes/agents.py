from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from tinyagentos.agent_db import find_agent, get_agent_summaries
from tinyagentos.config import save_config_locked, validate_agent_name

EXPORT_VERSION = 1

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
    """List all configured agents."""
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


@router.get("/api/agents/{name}/deploy-status")
async def get_deploy_status(request: Request, name: str):
    """Get the background deploy task status for an agent."""
    deploy_tasks = request.app.state.deploy_tasks
    task = deploy_tasks.get(name)
    if task is None:
        return JSONResponse({"error": f"No deploy task found for '{name}'"}, status_code=404)
    return task


@router.get("/api/agents/{name}")
async def get_agent_endpoint(request: Request, name: str):
    """Get agent details by name."""
    config = request.app.state.config
    agent = find_agent(config, name)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)
    return agent


@router.post("/api/agents")
async def add_agent(request: Request, body: AgentCreate):
    """Add a new agent to the configuration."""
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
    """Update an existing agent's configuration."""
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
    """Remove an agent from the configuration."""
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
    """Deploy a new agent -- creates LXC container, installs framework and QMD (background)."""
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

    # Add agent entry immediately with deploying status
    config.agents.append({
        "name": body.name,
        "host": "",
        "qmd_url": "",
        "color": body.color,
        "status": "deploying",
    })
    await save_config_locked(config, config.config_path)

    # Record deploy task
    deploy_tasks = request.app.state.deploy_tasks
    deploy_tasks[body.name] = {"status": "deploying", "name": body.name}

    from tinyagentos.deployer import deploy_agent, DeployRequest
    rkllama_url = "http://localhost:8080"
    for b in config.backends:
        if b.get("type") == "rkllama":
            rkllama_url = b["url"]
            break

    async def _background_deploy():
        try:
            result = await deploy_agent(DeployRequest(
                name=body.name,
                framework=body.framework,
                model=body.model,
                color=body.color,
                memory_limit=body.memory_limit,
                cpu_limit=body.cpu_limit,
                rkllama_url=rkllama_url,
            ))
            agent = find_agent(config, body.name)
            if result.get("success"):
                if agent is not None:
                    agent["host"] = result.get("ip", "")
                    agent["qmd_url"] = result.get("qmd_url", "")
                    agent["status"] = "running"
                deploy_tasks[body.name] = {"status": "success", "name": body.name, "result": result}
            else:
                if agent is not None:
                    agent["status"] = "failed"
                deploy_tasks[body.name] = {
                    "status": "failed",
                    "name": body.name,
                    "error": result.get("error", "unknown error"),
                }
        except Exception as exc:  # noqa: BLE001
            agent = find_agent(config, body.name)
            if agent is not None:
                agent["status"] = "failed"
            deploy_tasks[body.name] = {
                "status": "failed",
                "name": body.name,
                "error": str(exc),
            }
        finally:
            await save_config_locked(config, config.config_path)

    asyncio.create_task(_background_deploy())
    return {"status": "deploying", "name": body.name}


@router.post("/api/agents/{name}/start")
async def start_agent(request: Request, name: str):
    """Start an agent's LXC container."""
    from tinyagentos.containers import start_container
    return await start_container(f"agent-{name}")


@router.post("/api/agents/{name}/stop")
async def stop_agent(request: Request, name: str):
    """Stop an agent's LXC container."""
    from tinyagentos.containers import stop_container
    return await stop_container(f"agent-{name}")


@router.post("/api/agents/{name}/restart")
async def restart_agent(request: Request, name: str):
    """Restart an agent's LXC container."""
    from tinyagentos.containers import restart_container
    return await restart_container(f"agent-{name}")


@router.get("/api/partials/agent-logs/{name}", response_class=HTMLResponse)
async def agent_logs_partial(request: Request, name: str, lines: int = 100):
    """Agent logs as HTML partial for htmx."""
    from tinyagentos.containers import get_container_logs
    logs = await get_container_logs(f"agent-{name}", lines=lines)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "partials/agent_logs.html", {
        "name": name, "logs": logs,
    })


@router.get("/api/agents/{name}/logs")
async def agent_logs(request: Request, name: str, lines: int = 100):
    """Get recent journal logs from an agent's container."""
    from tinyagentos.containers import get_container_logs
    logs = await get_container_logs(f"agent-{name}", lines=lines)
    return {"name": name, "logs": logs}


@router.get("/api/agents/{name}/export")
async def export_agent(request: Request, name: str):
    """Export an agent's full config as portable JSON."""
    config = request.app.state.config
    agent = find_agent(config, name)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)

    # Gather channel assignments
    channel_store = request.app.state.channels
    channels = await channel_store.list_for_agent(name)
    channel_export = [
        {"type": ch["type"], "config": ch.get("config", {})}
        for ch in channels
    ]

    # Gather group memberships
    relationship_mgr = request.app.state.relationships
    groups = await relationship_mgr.get_agent_groups(name)
    group_names = [g["name"] for g in groups]

    return {
        "version": EXPORT_VERSION,
        "agent": {k: v for k, v in agent.items()},
        "channels": channel_export,
        "groups": group_names,
    }


class AgentImport(BaseModel):
    version: int = 1
    agent: dict
    channels: list[dict] = []
    groups: list[str] = []


@router.post("/api/agents/import")
async def import_agent(request: Request, body: AgentImport):
    """Import an agent from an exported JSON config."""
    config = request.app.state.config

    agent_data = body.agent
    name = agent_data.get("name", "")
    if not name:
        return JSONResponse({"error": "Agent name is required in export data"}, status_code=400)
    name_error = validate_agent_name(name)
    if name_error:
        return JSONResponse({"error": name_error}, status_code=400)
    if find_agent(config, name):
        return JSONResponse({"error": f"Agent '{name}' already exists"}, status_code=409)

    # Create the agent
    config.agents.append(agent_data)
    await save_config_locked(config, config.config_path)

    # Restore channel assignments
    channel_store = request.app.state.channels
    for ch in body.channels:
        await channel_store.add(name, ch.get("type", ""), ch.get("config", {}))

    # Restore group memberships
    relationship_mgr = request.app.state.relationships
    existing_groups = await relationship_mgr.list_groups()
    group_map = {g["name"]: g["id"] for g in existing_groups}
    for group_name in body.groups:
        if group_name in group_map:
            await relationship_mgr.add_member(group_map[group_name], name)

    return {"status": "imported", "name": name}


@router.delete("/api/agents/{name}/destroy")
async def destroy_agent(request: Request, name: str):
    """Destroy an agent -- stops and deletes the LXC container."""
    config = request.app.state.config
    from tinyagentos.deployer import undeploy_agent
    result = await undeploy_agent(name)
    if result["success"]:
        config.agents = [a for a in config.agents if a["name"] != name]
        await save_config_locked(config, config.config_path)
    return result
