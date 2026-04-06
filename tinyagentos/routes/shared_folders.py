from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/shared-folders", response_class=HTMLResponse)
async def shared_folders_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "shared_folders.html", {
        "active_page": "shared-folders",
    })


class CreateFolderRequest(BaseModel):
    name: str
    description: str = ""
    agents: list[str] | None = None


class GrantAccessRequest(BaseModel):
    agent_name: str
    permission: str = "readwrite"


@router.get("/api/shared-folders")
async def list_shared_folders(request: Request, agent_name: str | None = None):
    mgr = request.app.state.shared_folders
    folders = await mgr.list_folders(agent_name=agent_name)
    return folders


@router.post("/api/shared-folders")
async def create_shared_folder(request: Request, body: CreateFolderRequest):
    mgr = request.app.state.shared_folders
    try:
        folder_id = await mgr.create_folder(
            name=body.name,
            description=body.description,
            agents=body.agents,
        )
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return JSONResponse({"error": f"Folder '{body.name}' already exists"}, status_code=409)
        raise
    return {"id": folder_id, "status": "created"}


@router.delete("/api/shared-folders/{folder_id}")
async def delete_shared_folder(request: Request, folder_id: int):
    mgr = request.app.state.shared_folders
    deleted = await mgr.delete_folder(folder_id)
    if not deleted:
        return JSONResponse({"error": "Folder not found"}, status_code=404)
    return {"status": "deleted"}


@router.get("/api/shared-folders/{name}/files")
async def list_shared_folder_files(request: Request, name: str):
    mgr = request.app.state.shared_folders
    return mgr.list_files(name)


@router.post("/api/shared-folders/{name}/upload")
async def upload_to_shared_folder(request: Request, name: str, file: UploadFile):
    mgr = request.app.state.shared_folders
    folder_path = mgr.storage_dir / name
    if not folder_path.exists():
        return JSONResponse({"error": f"Folder '{name}' not found"}, status_code=404)
    dest = folder_path / file.filename
    content = await file.read()
    dest.write_bytes(content)
    return {"status": "uploaded", "name": file.filename, "size": len(content)}


@router.post("/api/shared-folders/{folder_id}/access")
async def grant_folder_access(request: Request, folder_id: int, body: GrantAccessRequest):
    mgr = request.app.state.shared_folders
    await mgr.grant_access(folder_id, body.agent_name, body.permission)
    return {"status": "granted"}
