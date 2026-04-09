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
    store = request.app.state.streaming_sessions
    session_id = await store.create_session(
        app_id=body.app_id,
        agent_name=body.agent_name,
        agent_type=body.agent_type,
        worker_name="local",
        container_id="pending",
    )
    return {"session_id": session_id, "status": "starting"}


@router.post("/api/streaming-apps/sessions/{session_id}/stop")
async def stop_session(request: Request, session_id: str):
    store = request.app.state.streaming_sessions
    session = await store.get_session(session_id)
    if session is None:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    await store.update_status(session_id, "stopped")
    return {"session_id": session_id, "status": "stopped"}


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
