from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from tinyagentos.agent_db import find_agent

logger = logging.getLogger(__name__)

router = APIRouter()


class SendMessageRequest(BaseModel):
    from_agent: str
    message: str
    tool_calls: list | None = None
    tool_results: list | None = None
    reasoning: str = ""
    depth: int = 2
    metadata: dict | None = None


@router.get("/agents/{name}/workspace", response_class=HTMLResponse)
async def workspace_page(request: Request, name: str):
    config = request.app.state.config
    agent = find_agent(config, name)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)
    templates = request.app.state.templates
    msg_store = request.app.state.agent_messages
    unread = await msg_store.unread_count(name)
    return templates.TemplateResponse(request, "workspace.html", {
        "active_page": "agents",
        "agent": agent,
        "unread_count": unread,
    })


@router.get("/agents/{name}/workspace/messages", response_class=HTMLResponse)
async def workspace_messages_page(request: Request, name: str, depth: int = 2):
    config = request.app.state.config
    agent = find_agent(config, name)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)
    templates = request.app.state.templates
    msg_store = request.app.state.agent_messages
    depth_level = max(1, min(3, depth))
    messages = await msg_store.get_messages(name, depth=depth_level)
    # Get list of conversation partners
    partners = set()
    for m in messages:
        if m["from"] != name:
            partners.add(m["from"])
        if m["to"] != name:
            partners.add(m["to"])
    all_agents = [a["name"] for a in config.agents if a["name"] != name]
    await msg_store.mark_read(name)
    return templates.TemplateResponse(request, "workspace_messages.html", {
        "active_page": "agents",
        "agent": agent,
        "messages": messages,
        "partners": sorted(partners),
        "all_agents": all_agents,
        "depth_level": depth_level,
    })


@router.get("/api/agents/{name}/messages")
async def api_agent_messages(request: Request, name: str, limit: int = 50, depth: int = 2):
    msg_store = request.app.state.agent_messages
    messages = await msg_store.get_messages(name, limit=limit, depth=depth)
    return messages


@router.get("/api/agents/{name}/files")
async def api_agent_files(request: Request, name: str):
    """List files in agent's workspace directory."""
    data_dir = request.app.state.config_path.parent
    workspace_dir = data_dir / "workspaces" / name
    if not workspace_dir.exists():
        return []
    files = []
    for f in sorted(workspace_dir.iterdir()):
        if f.is_file():
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "modified": f.stat().st_mtime,
            })
    return files


@router.post("/api/agents/{name}/messages")
async def api_send_message(request: Request, name: str, body: SendMessageRequest):
    msg_store = request.app.state.agent_messages
    msg_id = await msg_store.send(
        from_agent=body.from_agent,
        to_agent=name,
        message=body.message,
        tool_calls=body.tool_calls,
        tool_results=body.tool_results,
        reasoning=body.reasoning,
        depth=body.depth,
        metadata=body.metadata,
    )
    return {"id": msg_id, "status": "sent"}
