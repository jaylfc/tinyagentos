"""Routes for the openclaw bridge adapter.

Three endpoints called by the openclaw fork's taos-bridge.ts patch running
inside the agent container:

  GET  /api/openclaw/bootstrap              config snapshot on startup
  GET  /api/openclaw/sessions/{agent}/events  SSE stream of user messages
  POST /api/openclaw/sessions/{agent}/reply   reply ingestion

Auth: all three require a valid Bearer local token. The auth middleware already
handles most Bearer requests, but these endpoints also need an explicit 401
response for the events/reply paths where the middleware path might have gaps.
The bootstrap endpoint echoes the token back so the bridge can use it for the
two subsequent calls without reading the file again.

SSE implementation: hand-rolled via StreamingResponse with
media_type="text/event-stream". sse-starlette is not in pyproject so we avoid
the optional import.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter()
logger = logging.getLogger(__name__)


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _validate_bearer(request: Request) -> tuple[bool, str | None]:
    """Return (valid, token). Validates against the on-disk local token."""
    token = _bearer_token(request)
    if not token:
        return False, None
    auth_mgr = getattr(request.app.state, "auth", None)
    if auth_mgr is None:
        return False, None
    if auth_mgr.validate_local_token(token):
        return True, token
    return False, None


def _find_agent(config, slug: str) -> dict | None:
    agents = getattr(config, "agents", []) or []
    for a in agents:
        if a.get("name") == slug:
            return a
    return None


@router.get("/api/openclaw/bootstrap")
async def bootstrap(request: Request, agent: str | None = None):
    """Return the config snapshot openclaw needs on startup.

    MVP: ``?agent=<slug>`` selects the agent. Future: derive from a per-agent
    bearer token so the query param is not needed.

    Errors:
      404 — agent not found
      409 — agent found but llm_key missing (deploy incomplete)
      401 — bad or missing token
    """
    valid, token = _validate_bearer(request)
    if not valid:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    if not agent:
        return JSONResponse(
            {"error": "agent query parameter required"},
            status_code=400,
        )

    config = getattr(request.app.state, "config", None)
    agent_dict = _find_agent(config, agent) if config else None
    if agent_dict is None:
        return JSONResponse({"error": f"agent not found: {agent}"}, status_code=404)

    # llm_key may be null when no LiteLLM proxy is configured; fall back to
    # empty string so the gateway can start and openclaw can connect.
    llm_key = agent_dict.get("llm_key") or ""

    session_id = agent_dict.get("session_id") or agent

    base_url = "http://127.0.0.1:6969"

    return {
        "schema_version": 1,
        "agent_name": agent,
        "session_id": session_id,
        "models": {
            "providers": {
                "taos": {
                    "api": "openai-completions",
                    "baseUrl": "http://127.0.0.1:4000/v1",
                    "apiKey": llm_key,
                    "models": [],
                }
            }
        },
        "channel": {
            "provider": "taos",
            "events_url": f"{base_url}/api/openclaw/sessions/{agent}/events",
            "reply_url": f"{base_url}/api/openclaw/sessions/{agent}/reply",
            "auth_bearer": token,
        },
        "memory": None,
        "skills_mcp_url": None,
    }


@router.get("/api/openclaw/sessions/{agent}/events")
async def events_stream(request: Request, agent: str):
    """SSE stream of events for openclaw to consume.

    Openclaw connects once at startup and holds the connection. taOS pushes
    user_message and abort events; keepalive ticks fire every 15 s.

    Single-subscriber: a reconnect replaces the old connection's queue so the
    stale generator exits after draining the sentinel.
    """
    valid, _ = _validate_bearer(request)
    if not valid:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    registry = getattr(request.app.state, "bridge_sessions", None)
    if registry is None:
        return JSONResponse(
            {"error": "bridge session registry not initialised"},
            status_code=503,
        )

    async def event_generator():
        try:
            async for frame in registry.subscribe(agent):
                yield frame
                if await request.is_disconnected():
                    break
        except Exception:
            logger.exception("openclaw SSE generator error for agent %s", agent)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/openclaw/sessions/{agent}/reply")
async def reply_ingest(request: Request, agent: str):
    """Receive a reply payload from openclaw.

    Accepted kinds: delta, final, tool_call, tool_result, error, reasoning.
    All internal failures are caught in BridgeSessionRegistry.record_reply;
    this endpoint always returns 202 so openclaw does not retry indefinitely.
    """
    valid, _ = _validate_bearer(request)
    if not valid:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    registry = getattr(request.app.state, "bridge_sessions", None)
    if registry is None:
        logger.error("openclaw reply: bridge_sessions not on app.state")
        return JSONResponse({"accepted": True}, status_code=202)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    await registry.record_reply(agent, body)
    return JSONResponse({"accepted": True}, status_code=202)
