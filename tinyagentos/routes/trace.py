"""Trace write / read HTTP surface.

POST /api/trace — any taOS-owned caller records an event. agent_name
picks the per-agent, per-hour bucket in the home-folder mount.

GET /api/agents/{name}/trace — librarian reads structured history.

POST /api/lifecycle/notify — LiteLLM callback resets keep-alive timer.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from tinyagentos.trace_store import SCHEMA_VERSION, VALID_KINDS

logger = logging.getLogger(__name__)

router = APIRouter()


class TraceIn(BaseModel):
    agent_name: str
    kind: str
    id: str | None = None
    trace_id: str | None = None
    parent_id: str | None = None
    created_at: float | None = None
    channel_id: str | None = None
    thread_id: str | None = None
    backend_name: str | None = None
    model: str | None = None
    duration_ms: int | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    error: str | None = None
    payload: dict = Field(default_factory=dict)


@router.post("/api/trace")
async def post_trace(request: Request, body: TraceIn):
    registry = getattr(request.app.state, "trace_registry", None)
    if registry is None:
        return JSONResponse({"error": "trace registry not configured"}, status_code=503)
    if body.kind not in VALID_KINDS:
        return JSONResponse({"error": f"unknown kind {body.kind!r}"}, status_code=400)
    store = await registry.get(body.agent_name)
    env = await store.record(body.kind, **body.model_dump(exclude={"agent_name", "kind"}))
    return {"id": env["id"], "agent_name": body.agent_name, "schema_version": SCHEMA_VERSION}


@router.get("/api/agents/{name}/trace")
async def list_agent_trace(
    request: Request,
    name: str,
    kind: str | None = None,
    channel_id: str | None = None,
    trace_id: str | None = None,
    since: float | None = None,
    until: float | None = None,
    limit: int = 100,
):
    registry = getattr(request.app.state, "trace_registry", None)
    if registry is None:
        return JSONResponse({"error": "trace registry not configured"}, status_code=503)
    store = await registry.get(name)
    events = await store.list(
        kind=kind, channel_id=channel_id, trace_id=trace_id,
        since=since, until=until, limit=limit,
    )
    return {"agent_name": name, "schema_version": SCHEMA_VERSION, "events": events}


class LifecycleNotifyIn(BaseModel):
    backend_name: str


@router.post("/api/lifecycle/notify")
async def notify_lifecycle(request: Request, body: LifecycleNotifyIn):
    mgr = getattr(request.app.state, "lifecycle_manager", None)
    if mgr is None:
        return JSONResponse({"error": "lifecycle manager not configured"}, status_code=503)
    try:
        mgr.notify_task_complete(body.backend_name)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)
    return {"status": "noted", "backend_name": body.backend_name}
