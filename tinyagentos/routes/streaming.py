from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------

@router.get("/streaming", response_class=HTMLResponse)
async def streaming_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "streaming_apps.html", {
        "active_page": "streaming",
    })


@router.get("/app/{session_id}", response_class=HTMLResponse)
async def streaming_app_page(request: Request, session_id: str):
    store = request.app.state.streaming_sessions
    session = await store.get_session(session_id)
    if session is None:
        return HTMLResponse("Session not found", status_code=404)
    await store.touch_activity(session_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "streaming_app.html", {
        "session": session,
    })


# ---------------------------------------------------------------------------
# API — apps
# ---------------------------------------------------------------------------

@router.get("/api/streaming-apps")
async def list_streaming_apps(request: Request):
    registry = request.app.state.registry
    apps = []
    for app_manifest in registry.list_available():
        manifest = vars(app_manifest) if hasattr(app_manifest, "__dict__") else {}
        # Check if manifest dict has streaming key or type == streaming-app
        is_streaming = (
            getattr(app_manifest, "type", None) == "streaming-app"
            or "streaming" in manifest
        )
        if not is_streaming:
            continue
        apps.append({
            "id": app_manifest.id,
            "name": app_manifest.name,
            "description": app_manifest.description,
            "streaming": manifest.get("streaming"),
            "mcp": manifest.get("mcp"),
            "expert_agent": manifest.get("expert_agent"),
        })
    return {"apps": apps}


# ---------------------------------------------------------------------------
# API — sessions
# ---------------------------------------------------------------------------

@router.get("/api/streaming-apps/sessions")
async def list_sessions(request: Request, active_only: bool = False):
    store = request.app.state.streaming_sessions
    sessions = await store.list_sessions(active_only=active_only)
    return {"sessions": sessions}


@router.get("/api/streaming-apps/sessions/{session_id}")
async def get_session(request: Request, session_id: str):
    store = request.app.state.streaming_sessions
    session = await store.get_session(session_id)
    if session is None:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return session


class LaunchRequest(BaseModel):
    app_id: str
    agent_name: str = "default"
    agent_type: str = "app-expert"


@router.post("/api/streaming-apps/launch")
async def launch_session(request: Request, body: LaunchRequest):
    orchestrator = request.app.state.app_orchestrator
    # Get app manifest from registry if available
    registry = request.app.state.registry
    manifest = {}
    for app in registry.list_available():
        m = getattr(app, "manifest", {}) or {}
        if app.id == body.app_id or m.get("id") == body.app_id:
            manifest = m
            break

    agent_name = body.agent_name or f"{body.app_id}-expert"
    result = await orchestrator.launch(
        app_id=body.app_id,
        app_manifest=manifest,
        agent_name=agent_name,
        agent_type=body.agent_type,
    )
    return result


@router.post("/api/streaming-apps/sessions/{session_id}/stop")
async def stop_session(request: Request, session_id: str):
    orchestrator = request.app.state.app_orchestrator
    result = await orchestrator.stop(session_id)
    if "error" in result:
        return JSONResponse(result, status_code=404)
    return result


class SwapAgentRequest(BaseModel):
    agent_name: str
    agent_type: str = "app-expert"


@router.post("/api/streaming-apps/sessions/{session_id}/swap-agent")
async def swap_agent(request: Request, session_id: str, body: SwapAgentRequest):
    store = request.app.state.streaming_sessions
    session = await store.get_session(session_id)
    if session is None:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    await store.swap_agent(session_id, body.agent_name, body.agent_type)
    return {"session_id": session_id, "agent_name": body.agent_name, "agent_type": body.agent_type}


# ---------------------------------------------------------------------------
# API — expert agents
# ---------------------------------------------------------------------------

@router.get("/api/streaming-apps/experts")
async def list_experts(request: Request):
    store = request.app.state.expert_agents
    agents = await store.list_all()
    return {"experts": agents}


@router.get("/api/streaming-apps/experts/{app_id}")
async def get_expert(request: Request, app_id: str):
    store = request.app.state.expert_agents
    agent = await store.get_by_app(app_id)
    if agent is None:
        return JSONResponse({"error": "Expert agent not found"}, status_code=404)
    return agent


class UpdatePromptRequest(BaseModel):
    system_prompt: str


@router.put("/api/streaming-apps/experts/{app_id}/prompt")
async def update_expert_prompt(request: Request, app_id: str, body: UpdatePromptRequest):
    store = request.app.state.expert_agents
    agent = await store.get_by_app(app_id)
    if agent is None:
        return JSONResponse({"error": "Expert agent not found"}, status_code=404)
    await store.update_prompt(app_id, body.system_prompt)
    return {"app_id": app_id, "system_prompt": body.system_prompt}


@router.post("/api/streaming-apps/experts/{app_id}/reset")
async def reset_expert(request: Request, app_id: str):
    store = request.app.state.expert_agents
    agent = await store.get_by_app(app_id)
    if agent is None:
        return JSONResponse({"error": "Expert agent not found"}, status_code=404)
    await store.reset(app_id)
    return {"app_id": app_id, "status": "reset"}


# ---------------------------------------------------------------------------
# API — companion launcher
# ---------------------------------------------------------------------------

@router.get("/api/streaming-apps/launcher")
async def launcher_data(request: Request):
    """Data for the companion app launcher dropdown."""
    registry = request.app.state.registry
    streaming_store = request.app.state.streaming_sessions

    # Available apps
    apps = []
    for app in registry.list_available():
        manifest = getattr(app, "manifest", {}) or {}
        if manifest.get("type") == "streaming-app" or manifest.get("streaming"):
            apps.append({"id": app.id, "name": app.name})

    # Active sessions
    sessions = await streaming_store.list_sessions(active_only=True)

    # Agents
    config = request.app.state.config
    agents = [{"name": a["name"], "status": a.get("status", "configured")} for a in config.agents]

    return {"apps": apps, "sessions": sessions, "agents": agents}
