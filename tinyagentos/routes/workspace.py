from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from tinyagentos.agent_db import find_agent

logger = logging.getLogger(__name__)

router = APIRouter()

WORKSPACE_DIR_NAME = "agent-workspaces"


def _workspace_dir(request: Request, agent_name: str) -> Path:
    """Resolve the workspace directory for an agent, creating on first access."""
    data_dir = request.app.state.config_path.parent
    ws = data_dir / WORKSPACE_DIR_NAME / agent_name
    ws.mkdir(parents=True, exist_ok=True)
    return ws


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


# ---------------------------------------------------------------------------
# Messages view
# ---------------------------------------------------------------------------


@router.get("/agents/{name}/workspace/messages", response_class=HTMLResponse)
async def workspace_messages_page(request: Request, name: str, depth: int = 2):
    config = request.app.state.config
    agent = find_agent(config, name)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)
    templates = request.app.state.templates
    msg_store = request.app.state.agent_messages
    depth_level = max(1, min(3, depth))

    # If a specific conversation partner is selected, get that conversation
    selected = request.query_params.get("with", "")
    if selected:
        messages = await msg_store.get_conversation(name, selected, depth=depth_level)
    else:
        messages = await msg_store.get_messages(name, depth=depth_level)

    contacts = await msg_store.get_contacts(name)
    all_agents = [a["name"] for a in config.agents if a["name"] != name]
    partners = sorted({c["name"] for c in contacts})

    await msg_store.mark_read(name)
    return templates.TemplateResponse(request, "workspace_messages.html", {
        "active_page": "agents",
        "agent": agent,
        "messages": messages,
        "partners": partners,
        "contacts": contacts,
        "all_agents": all_agents,
        "depth_level": depth_level,
        "selected_partner": selected,
    })


@router.get("/agents/{name}/workspace/messages/{other_agent}", response_class=HTMLResponse)
async def workspace_messages_conversation(request: Request, name: str, other_agent: str, depth: int = 2):
    """Conversation with a specific agent (path-based URL)."""
    config = request.app.state.config
    agent = find_agent(config, name)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)
    templates = request.app.state.templates
    msg_store = request.app.state.agent_messages
    depth_level = max(1, min(3, depth))

    messages = await msg_store.get_conversation(name, other_agent, depth=depth_level)
    contacts = await msg_store.get_contacts(name)
    all_agents = [a["name"] for a in config.agents if a["name"] != name]
    partners = sorted({c["name"] for c in contacts})

    await msg_store.mark_read(name)
    return templates.TemplateResponse(request, "workspace_messages.html", {
        "active_page": "agents",
        "agent": agent,
        "messages": messages,
        "partners": partners,
        "contacts": contacts,
        "all_agents": all_agents,
        "depth_level": depth_level,
        "selected_partner": other_agent,
    })


@router.get("/api/agents/{name}/workspace/messages/contacts")
async def api_agent_contacts(request: Request, name: str):
    """List agents this agent has communicated with + unread counts."""
    msg_store = request.app.state.agent_messages
    contacts = await msg_store.get_contacts(name)
    return contacts


@router.get("/api/agents/{name}/messages")
async def api_agent_messages(request: Request, name: str, limit: int = 50, depth: int = 2):
    msg_store = request.app.state.agent_messages
    messages = await msg_store.get_messages(name, limit=limit, depth=depth)
    return messages


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


# ---------------------------------------------------------------------------
# Files view
# ---------------------------------------------------------------------------


@router.get("/agents/{name}/workspace/files", response_class=HTMLResponse)
async def workspace_files_page(request: Request, name: str):
    config = request.app.state.config
    agent = find_agent(config, name)
    if not agent:
        return JSONResponse({"error": f"Agent '{name}' not found"}, status_code=404)
    templates = request.app.state.templates
    ws_dir = _workspace_dir(request, name)

    # List files in agent workspace
    files = []
    for f in sorted(ws_dir.iterdir()):
        if f.is_file():
            stat = f.stat()
            files.append({
                "name": f.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })

    # Get shared folders this agent has access to
    shared_folders_mgr = request.app.state.shared_folders
    shared_folders = await shared_folders_mgr.list_folders(agent_name=name)

    return templates.TemplateResponse(request, "workspace_files.html", {
        "active_page": "agents",
        "agent": agent,
        "files": files,
        "shared_folders": shared_folders,
    })


@router.get("/api/agents/{name}/workspace/files")
async def api_workspace_files(request: Request, name: str):
    """List files in agent's workspace directory."""
    ws_dir = _workspace_dir(request, name)
    files = []
    for f in sorted(ws_dir.iterdir()):
        if f.is_file():
            stat = f.stat()
            files.append({
                "name": f.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
    return files


@router.post("/api/agents/{name}/workspace/files/upload")
async def api_workspace_upload(request: Request, name: str, file: UploadFile = File(...)):
    """Upload a file to agent's workspace directory."""
    ws_dir = _workspace_dir(request, name)
    dest = ws_dir / file.filename
    content = await file.read()
    dest.write_bytes(content)
    return {"name": file.filename, "size": len(content), "status": "uploaded"}


@router.delete("/api/agents/{name}/workspace/files/{filename}")
async def api_workspace_delete(request: Request, name: str, filename: str):
    """Delete a file from agent's workspace directory."""
    ws_dir = _workspace_dir(request, name)
    target = ws_dir / filename
    # Prevent path traversal
    if not target.resolve().is_relative_to(ws_dir.resolve()):
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    if not target.exists():
        return JSONResponse({"error": f"File '{filename}' not found"}, status_code=404)
    target.unlink()
    return {"name": filename, "status": "deleted"}


# Keep legacy files endpoint for backward compatibility
@router.get("/api/agents/{name}/files")
async def api_agent_files(request: Request, name: str):
    """List files in agent's workspace directory (legacy endpoint)."""
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
