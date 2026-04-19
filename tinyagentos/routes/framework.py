from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from tinyagentos.agent_db import find_agent

router = APIRouter()


def _installed(agent):
    return {"tag": agent.get("framework_version_tag"),
            "sha": agent.get("framework_version_sha")}


def _latest(entry):
    if entry is None:
        return None
    return {"tag": entry["tag"], "sha": entry["sha"],
            "published_at": entry.get("published_at")}


@router.get("/api/agents/{slug}/framework")
async def get_agent_framework(request: Request, slug: str):
    config = request.app.state.config
    agent = find_agent(config, slug)
    if not agent:
        return JSONResponse({"error": "agent not found"}, status_code=404)
    fw_id = agent.get("framework")
    cache = getattr(request.app.state, "latest_framework_versions", {}) or {}
    latest = cache.get(fw_id)
    installed = _installed(agent)
    update_available = bool(
        latest and installed["sha"] and latest["sha"] != installed["sha"]
    )
    return {
        "framework": fw_id,
        "installed": installed,
        "latest": _latest(latest),
        "update_available": update_available,
        "update_status": agent.get("framework_update_status", "idle"),
        "update_started_at": agent.get("framework_update_started_at"),
        "last_error": agent.get("framework_update_last_error"),
        "last_snapshot": agent.get("framework_last_snapshot"),
    }
