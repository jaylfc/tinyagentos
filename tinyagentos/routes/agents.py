from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tinyagentos.agent_db import find_agent, get_agent_summaries
from tinyagentos.config import save_config_locked, validate_agent_name, slugify_agent_name

EXPORT_VERSION = 1

router = APIRouter()


class AgentCreate(BaseModel):
    name: str
    host: str
    qmd_index: str
    color: str = "#888888"
    can_read_user_memory: bool = False


class AgentUpdate(BaseModel):
    host: str | None = None
    qmd_index: str | None = None
    color: str | None = None
    can_read_user_memory: bool | None = None


@router.get("/api/agents")
async def list_agents(request: Request):
    """List all configured agents."""
    return request.app.state.config.agents


@router.get("/api/agents/containers")
async def list_agent_containers(request: Request):
    """List live LXC container status for all agent containers."""
    from tinyagentos.containers import list_containers
    containers = await list_containers(prefix="taos-agent-")
    return [
        {
            "name": c.name,
            "agent_name": c.name.removeprefix("taos-agent-"),
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
    """Add a new agent to the configuration.

    The user-supplied name is stored verbatim as ``display_name`` for UI
    purposes and slugified into ``name`` for container and path safety.
    If the slug collides with an existing agent, a numeric suffix is
    appended until it's unique.
    """
    config = request.app.state.config
    display_name = body.name.strip()
    name_error = validate_agent_name(display_name)
    if name_error:
        return JSONResponse({"error": name_error}, status_code=400)

    slug = slugify_agent_name(display_name)
    unique_slug = slug
    suffix = 2
    while find_agent(config, unique_slug):
        unique_slug = f"{slug}-{suffix}"
        suffix += 1
        if suffix > 100:
            return JSONResponse({"error": "Could not generate a unique agent slug"}, status_code=400)

    agent = body.model_dump()
    agent["name"] = unique_slug
    agent["display_name"] = display_name
    config.agents.append(agent)
    await save_config_locked(config, config.config_path)
    return {"status": "created", "name": unique_slug, "display_name": display_name}


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
    if body.can_read_user_memory is not None:
        agent["can_read_user_memory"] = body.can_read_user_memory
    await save_config_locked(config, config.config_path)
    return {"status": "updated", "name": name}


class AgentPermissions(BaseModel):
    can_read_user_memory: bool | None = None


@router.put("/api/agents/{name}/permissions")
async def update_agent_permissions(request: Request, name: str, body: AgentPermissions):
    """Update an agent's permissions (e.g. user memory access)."""
    config = request.app.state.config
    agent = find_agent(config, name)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)
    if body.can_read_user_memory is not None:
        agent["can_read_user_memory"] = body.can_read_user_memory
    await save_config_locked(config, config.config_path)
    return {
        "status": "updated",
        "name": name,
        "permissions": {
            "can_read_user_memory": agent.get("can_read_user_memory", False),
        },
    }


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
    can_read_user_memory: bool = False
    # Optional pin: user explicitly picked a specific worker to run on.
    # None means "controller decides" (and for worker-hosted models the
    # controller will route to wherever the model already lives).
    target_worker: str | None = None
    # Worker failure policy fields (added in worker-failure-handling).
    on_worker_failure: str = "pause"
    fallback_models: list[str] = []


@router.post("/api/agents/deploy")
async def deploy_agent_endpoint(request: Request, body: DeployAgentRequest):
    """Deploy a new agent.

    Resolution order for the requested model (task #176 route-only stub):

    1. Controller-local model — runs on the controller like today.
    2. Cloud provider model (openai / anthropic / litellm) — unchanged,
       LiteLLM proxy handles it on the controller.
    3. Worker-hosted model, no ``target_worker`` pin — route to the
       worker that holds the model and return 202. The actual remote
       launch is deferred to Phase 1.5; for now we return the holder's
       name so the caller (and the user) knows where the agent needs
       to land.
    4. Worker-hosted model, ``target_worker`` pinned AND that worker has
       the model — runs on the pinned worker (also 202 stub today).
    5. Worker-hosted model, ``target_worker`` pinned but that worker
       does NOT have the model — 409 with the list of workers that do.
       We never silently retarget a pinned deploy.
    6. Model not found anywhere in the cluster — 404.
    """
    config = request.app.state.config
    display_name = body.name.strip()
    name_error = validate_agent_name(display_name)
    if name_error:
        return JSONResponse({"error": name_error}, status_code=400)
    # Derive a container-safe slug and ensure uniqueness
    slug = slugify_agent_name(display_name)
    unique_slug = slug
    suffix = 2
    while find_agent(config, unique_slug):
        unique_slug = f"{slug}-{suffix}"
        suffix += 1
        if suffix > 100:
            return JSONResponse({"error": "Could not generate a unique agent slug"}, status_code=400)
    # Rewrite body.name to the unique slug; the original user-entered name
    # is preserved as display_name for the UI.
    body.name = unique_slug
    # Validate framework against catalog instead of hardcoded list
    if body.framework != "none":
        registry = request.app.state.registry
        known = {a.id for a in registry.list_available(type_filter="agent-framework")}
        if body.framework not in known:
            return JSONResponse({"error": f"Unknown framework '{body.framework}'. Available: {sorted(known)}"}, status_code=400)

    # ------------------------------------------------------------------
    # Cross-worker deploy routing (task #176 stub)
    # ------------------------------------------------------------------
    # Resolve the requested model's host BEFORE we touch config or kick
    # off a background deploy. If the model lives on a remote worker we
    # need to either route there (no local container) or reject the
    # deploy with a clear 409 when the user's pin conflicts with where
    # the model actually is.
    if body.model:
        from tinyagentos.cluster.model_resolver import find_model_hosts

        cluster = getattr(request.app.state, "cluster_manager", None)
        catalog = getattr(request.app.state, "backend_catalog", None)
        local_models = catalog.all_models() if catalog is not None else []

        # Cloud model ids are whatever openai/anthropic-typed backends
        # advertise. Keep this a best-effort: missing provider state just
        # means cloud models resolve as "not_found" and the caller can
        # retry once providers are configured.
        cloud_models: list[str] = []
        try:
            for b in config.backends or []:
                if b.get("type") in ("openai", "anthropic"):
                    for m in b.get("models") or []:
                        if isinstance(m, dict):
                            mid = m.get("id") or m.get("name") or ""
                        else:
                            mid = str(m)
                        if mid:
                            cloud_models.append(mid)
        except Exception:  # noqa: BLE001
            pass

        location = find_model_hosts(
            body.model,
            cluster_state=cluster,
            local_models=local_models,
            cloud_models=cloud_models,
        )

        if location.kind == "not_found":
            return JSONResponse(
                {
                    "error": (
                        f"model '{body.model}' was not found on the controller, "
                        f"on any online worker, or among configured cloud providers. "
                        f"Download it first or pick a model that is already in the cluster."
                    ),
                },
                status_code=404,
            )

        if location.kind == "worker":
            # Case 5: pin conflict — user asked for a specific worker
            # that does not hold the model.
            if body.target_worker and body.target_worker not in location.hosts:
                return JSONResponse(
                    {
                        "error": (
                            f"model '{body.model}' is not on worker "
                            f"'{body.target_worker}'. It is available on: "
                            f"{location.hosts}. Deploy there, or wait for "
                            f"Phase 1.5 network model placement."
                        ),
                        "model": body.model,
                        "pinned_worker": body.target_worker,
                        "available_on": location.hosts,
                    },
                    status_code=409,
                )

            # Cases 3 + 4: route to the worker that holds the model.
            # Phase 1.5 will actually instruct the worker to launch; for
            # now we return a 202 naming the destination so the caller
            # knows where the agent needs to land. Deliberately do NOT
            # add a local agent entry — a ghost entry on the controller
            # for an agent that lives on Fedora would confuse both the
            # UI and the LXC bulk-ops endpoints.
            chosen = body.target_worker or location.canonical_host
            return JSONResponse(
                {
                    "status": "routed",
                    "name": body.name,
                    "model": body.model,
                    "worker": chosen,
                    "available_on": location.hosts,
                    "message": (
                        f"model '{body.model}' lives on worker '{chosen}'. "
                        f"Routed deploy target only — remote launch lands "
                        f"with Phase 1.5 network model placement."
                    ),
                },
                status_code=202,
            )
        # kind == "controller" or "cloud": fall through to the unchanged
        # controller-local deploy path below.

    # Add agent entry immediately with deploying status. qmd_url has
    # been removed from the agent schema — every agent reads and writes
    # through the shared host qmd.service, addressed by agent name and
    # the bind-mounted per-agent SQLite at /memory. See
    # docs/design/framework-agnostic-runtime.md.
    from tinyagentos.config import normalize_agent
    new_agent = normalize_agent({
        "name": body.name,
        "display_name": display_name,
        "host": "",
        "color": body.color,
        "status": "deploying",
        "can_read_user_memory": body.can_read_user_memory,
        "on_worker_failure": body.on_worker_failure,
        "fallback_models": [m for m in body.fallback_models if m],
    })
    config.agents.append(new_agent)
    await save_config_locked(config, config.config_path)

    # Record deploy task
    deploy_tasks = request.app.state.deploy_tasks
    deploy_tasks[body.name] = {"status": "deploying", "name": body.name}

    from tinyagentos.deployer import deploy_agent, DeployRequest
    data_dir = request.app.state.data_dir
    llm_proxy = getattr(request.app.state, "llm_proxy", None)

    async def _background_deploy():
        try:
            result = await deploy_agent(DeployRequest(
                name=body.name,
                framework=body.framework,
                model=body.model,
                data_dir=data_dir,
                color=body.color,
                memory_limit=body.memory_limit,
                cpu_limit=body.cpu_limit,
                extra_config={"llm_proxy": llm_proxy} if llm_proxy else None,
                can_read_user_memory=body.can_read_user_memory,
            ))
            agent = find_agent(config, body.name)
            if result.get("success"):
                if agent is not None:
                    agent["host"] = result.get("ip", "")
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


@router.post("/api/agents/bulk/start")
async def bulk_start_agents(request: Request):
    """Start all agent containers."""
    from tinyagentos.containers import start_container
    config = request.app.state.config
    results = {}
    for agent in config.agents:
        name = agent["name"]
        try:
            result = await start_container(f"taos-agent-{name}")
            results[name] = {"success": result.get("success", False)}
        except Exception as e:
            results[name] = {"success": False, "error": str(e)}
    return {"action": "start", "results": results}


@router.post("/api/agents/bulk/stop")
async def bulk_stop_agents(request: Request):
    """Stop all agent containers, running graceful prepare first."""
    from tinyagentos.containers import stop_container
    config = request.app.state.config
    orchestrator = getattr(request.app.state, "orchestrator", None)
    report = {}
    if orchestrator is not None:
        report = await orchestrator.prepare("all", "stop")
    results = {}
    for agent in config.agents:
        name = agent["name"]
        try:
            result = await stop_container(f"taos-agent-{name}")
            results[name] = {"success": result.get("success", False)}
        except Exception as e:
            results[name] = {"success": False, "error": str(e)}
    return {"action": "stop", "prepare_report": report, "results": results}


@router.post("/api/agents/bulk/restart")
async def bulk_restart_agents(request: Request):
    """Restart all agent containers."""
    from tinyagentos.containers import restart_container
    config = request.app.state.config
    results = {}
    for agent in config.agents:
        name = agent["name"]
        try:
            result = await restart_container(f"taos-agent-{name}")
            results[name] = {"success": result.get("success", False)}
        except Exception as e:
            results[name] = {"success": False, "error": str(e)}
    return {"action": "restart", "results": results}


@router.post("/api/agents/{name}/start")
async def start_agent(request: Request, name: str):
    """Start an agent's LXC container."""
    from tinyagentos.containers import start_container
    return await start_container(f"taos-agent-{name}")


@router.post("/api/agents/{name}/pause")
async def pause_agent(request: Request, name: str):
    """Gracefully prepare an agent for pause (paused=True, container still running)."""
    config = request.app.state.config
    agent = find_agent(config, name)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)
    orchestrator = getattr(request.app.state, "orchestrator", None)
    report = {}
    if orchestrator is not None:
        report = await orchestrator.prepare([name], "pause")
    return {"status": "paused", "name": name, "report": report}


@router.post("/api/agents/{name}/stop")
async def stop_agent(request: Request, name: str):
    """Gracefully prepare then stop an agent's LXC container."""
    from tinyagentos.containers import stop_container
    config = request.app.state.config
    agent = find_agent(config, name)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)
    orchestrator = getattr(request.app.state, "orchestrator", None)
    report = {}
    if orchestrator is not None:
        report = await orchestrator.prepare([name], "stop")
    stop_result = await stop_container(f"taos-agent-{name}")
    return {"prepare_report": report, "stop_result": stop_result}


@router.post("/api/agents/{name}/restart")
async def restart_agent(request: Request, name: str):
    """Restart an agent's LXC container."""
    from tinyagentos.containers import restart_container
    return await restart_container(f"taos-agent-{name}")


@router.get("/api/agents/{name}/logs")
async def agent_logs(request: Request, name: str, lines: int = 100):
    """Get recent journal logs from an agent's container."""
    from tinyagentos.containers import get_container_logs
    logs = await get_container_logs(f"taos-agent-{name}", lines=lines)
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


@router.post("/api/agents/{name}/resume")
async def resume_agent(request: Request, name: str):
    """Clear the paused flag on an agent, allowing it to accept new calls."""
    config = request.app.state.config
    agent = find_agent(config, name)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)
    if not agent.get("paused", False):
        return {"status": "ok", "name": name, "paused": False}
    agent["paused"] = False
    await save_config_locked(config, config.config_path)
    return {"status": "resumed", "name": name, "paused": False}


class AgentModelUpdate(BaseModel):
    model: str


@router.post("/api/agents/{name}/model")
async def update_agent_model(request: Request, name: str, body: AgentModelUpdate):
    """Update an agent's primary model and resume it if it was paused.

    Validates the requested model against currently-reachable cluster models
    (local backend catalog + online workers).  Returns 409 if the model is
    not reachable anywhere in the cluster right now.
    """
    config = request.app.state.config
    agent = find_agent(config, name)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)

    model_id = body.model.strip()
    if not model_id:
        return JSONResponse({"error": "model must not be empty"}, status_code=400)

    # Validate reachability against the live cluster state.
    from tinyagentos.cluster.model_resolver import find_model_hosts

    cluster = getattr(request.app.state, "cluster_manager", None)
    catalog = getattr(request.app.state, "backend_catalog", None)
    local_models = catalog.all_models() if catalog is not None else []

    cloud_models: list[str] = []
    try:
        for b in config.backends or []:
            if b.get("type") in ("openai", "anthropic"):
                for m in b.get("models") or []:
                    mid = (m.get("id") or m.get("name") or "") if isinstance(m, dict) else str(m)
                    if mid:
                        cloud_models.append(mid)
    except Exception:  # noqa: BLE001
        pass

    location = find_model_hosts(
        model_id,
        cluster_state=cluster,
        local_models=local_models,
        cloud_models=cloud_models,
    )

    if location.kind == "not_found":
        return JSONResponse(
            {
                "error": (
                    f"model '{model_id}' is not reachable anywhere in the cluster right now. "
                    f"Make sure the model is downloaded and the worker is online."
                ),
                "model": model_id,
            },
            status_code=409,
        )

    # Update the agent's model and clear the paused flag so it can
    # immediately start accepting calls on the new model.
    agent["model"] = model_id
    was_paused = agent.get("paused", False)
    agent["paused"] = False
    await save_config_locked(config, config.config_path)

    return {
        "status": "updated",
        "name": name,
        "model": model_id,
        "resumed": was_paused,
        "location": location.kind,
    }
