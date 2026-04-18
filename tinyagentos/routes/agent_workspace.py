from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from tinyagentos.routes.user_workspace import (
    _dir_signature,
    _list_dir,
    _resolve_safe,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class MkdirRequest(BaseModel):
    path: str


def _agent_exists(request: Request, agent_name: str) -> bool:
    """Check the agent is in the deploy registry (config.agents)."""
    config = getattr(request.app.state, "config", None)
    if config is None:
        return False
    agents = getattr(config, "agents", None) or []
    return any(a.get("name") == agent_name for a in agents)


def _get_agent_workspace_root(request: Request, agent_name: str) -> Path | None:
    """Resolve the workspace root for an agent.

    Returns None if the agent name would escape the base directory (e.g.
    path traversal in the slug) or resolves outside the base. Creates the
    directory on first access for parity with the user workspace.
    """
    base = Path(request.app.state.agent_workspaces_dir)
    try:
        candidate = (base / agent_name).resolve()
        if not candidate.is_relative_to(base.resolve()):
            return None
    except Exception:
        return None
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def _resolve_workspace(request: Request, agent_name: str) -> tuple[Path | None, JSONResponse | None]:
    """Validate the agent and return its workspace root.

    Returns ``(workspace, None)`` on success, or ``(None, error_response)``
    on failure. Keeps the route bodies free of repeated validation boilerplate.
    """
    if not _agent_exists(request, agent_name):
        return None, JSONResponse({"error": f"Agent '{agent_name}' not found"}, status_code=404)
    workspace = _get_agent_workspace_root(request, agent_name)
    if workspace is None:
        return None, JSONResponse({"error": "Invalid agent name"}, status_code=400)
    return workspace, None


@router.get("/api/agents/{agent_name}/workspace/files")
async def api_list_files(request: Request, agent_name: str, path: str = ""):
    """List files and directories in an agent's workspace."""
    workspace, err = _resolve_workspace(request, agent_name)
    if err is not None:
        return err
    result = _list_dir(workspace, path)
    if isinstance(result, tuple):
        status, body = result
        return JSONResponse(body, status_code=status)
    return result


@router.get("/api/agents/{agent_name}/workspace/files/watch")
async def api_watch_files(request: Request, agent_name: str, path: str = "", interval: float = 1.0):
    """SSE stream of directory listing changes for an agent workspace."""
    workspace, err = _resolve_workspace(request, agent_name)
    if err is not None:
        return err
    interval = max(0.25, min(interval, 10.0))

    async def event_stream():
        last_signature: str | None = None
        try:
            while True:
                if await request.is_disconnected():
                    break
                result = _list_dir(workspace, path)
                if isinstance(result, tuple):
                    status, body = result
                    yield f"event: error\ndata: {json.dumps(body)}\n\n"
                    break
                entries = result
                signature = _dir_signature(entries)
                if signature != last_signature:
                    last_signature = signature
                    yield f"data: {json.dumps(entries)}\n\n"
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/agents/{agent_name}/workspace/files/upload")
async def api_upload_file(request: Request, agent_name: str, path: str = "", file: UploadFile = File(...)):
    """Upload a file into an agent's workspace, optionally into a subdirectory."""
    workspace, err = _resolve_workspace(request, agent_name)
    if err is not None:
        return err

    if path:
        target_dir = _resolve_safe(workspace, path)
        if target_dir is None:
            return JSONResponse({"error": "Invalid path"}, status_code=400)
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = workspace

    filename = Path(file.filename).name  # strip any path component
    dest = target_dir / filename
    content = await file.read()
    dest.write_bytes(content)
    rel = dest.relative_to(workspace)

    return {"name": filename, "path": str(rel), "size": len(content), "status": "uploaded"}


@router.post("/api/agents/{agent_name}/workspace/mkdir")
async def api_mkdir(request: Request, agent_name: str, body: MkdirRequest):
    """Create a directory inside an agent's workspace."""
    workspace, err = _resolve_workspace(request, agent_name)
    if err is not None:
        return err

    if not body.path or not body.path.strip():
        return JSONResponse({"error": "path is required"}, status_code=400)

    target = _resolve_safe(workspace, body.path.strip())
    if target is None:
        return JSONResponse({"error": "Invalid path"}, status_code=400)

    target.mkdir(parents=True, exist_ok=True)
    rel = target.relative_to(workspace)
    return {"path": str(rel), "status": "created"}


@router.get("/api/agents/{agent_name}/workspace/stats")
async def api_workspace_stats(request: Request, agent_name: str):
    """Return total file count and total size of an agent's workspace."""
    workspace, err = _resolve_workspace(request, agent_name)
    if err is not None:
        return err

    total_files = 0
    total_size = 0
    for item in workspace.rglob("*"):
        if item.is_file():
            total_files += 1
            total_size += item.stat().st_size

    return {
        "total_files": total_files,
        "total_size": total_size,
    }


@router.get("/api/agents/{agent_name}/workspace/files/{file_path:path}")
async def api_get_file(request: Request, agent_name: str, file_path: str):
    """Stream a single file from an agent's workspace."""
    workspace, err = _resolve_workspace(request, agent_name)
    if err is not None:
        return err
    target = _resolve_safe(workspace, file_path)
    if target is None:
        return JSONResponse({"error": "Invalid path"}, status_code=400)
    if not target.exists() or not target.is_file():
        return JSONResponse({"error": f"'{file_path}' not found"}, status_code=404)
    return FileResponse(target, filename=target.name)


@router.delete("/api/agents/{agent_name}/workspace/files/{file_path:path}")
async def api_delete_file(request: Request, agent_name: str, file_path: str):
    """Delete a file or directory from an agent's workspace."""
    workspace, err = _resolve_workspace(request, agent_name)
    if err is not None:
        return err

    target = _resolve_safe(workspace, file_path)
    if target is None:
        return JSONResponse({"error": "Invalid path"}, status_code=400)

    if not target.exists():
        return JSONResponse({"error": f"'{file_path}' not found"}, status_code=404)

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    return {"path": file_path, "status": "deleted"}
