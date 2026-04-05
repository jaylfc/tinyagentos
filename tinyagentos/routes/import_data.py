from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".html", ".json", ".csv"}
UPLOAD_DIR = Path(tempfile.gettempdir()) / "tinyagentos_imports"


@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request):
    templates = request.app.state.templates
    config = request.app.state.config
    agents = [a["name"] for a in config.agents]
    return templates.TemplateResponse(request, "import.html", {
        "active_page": "import",
        "agents": agents,
    })


@router.post("/api/import/upload")
async def upload_file(request: Request, file: UploadFile):
    if not file.filename:
        return JSONResponse({"error": "No file provided"}, status_code=400)

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return JSONResponse(
            {"error": f"Unsupported format '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"},
            status_code=400,
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    size = dest.stat().st_size
    return {
        "status": "uploaded",
        "filename": file.filename,
        "size": size,
        "path": str(dest),
    }


@router.post("/api/import/embed")
async def embed_files(request: Request):
    body = await request.json()
    agent_name = body.get("agent_name")
    filenames = body.get("files", [])

    if not agent_name:
        return JSONResponse({"error": "agent_name is required"}, status_code=400)
    if not filenames:
        return JSONResponse({"error": "No files specified"}, status_code=400)

    # Verify files exist
    missing = [f for f in filenames if not (UPLOAD_DIR / f).exists()]
    if missing:
        return JSONResponse({"error": f"Files not found: {', '.join(missing)}"}, status_code=404)

    # In a real deployment, this would call the agent's qmd serve to embed.
    # For now, return success with file list.
    embedded = []
    for fname in filenames:
        fpath = UPLOAD_DIR / fname
        embedded.append({"filename": fname, "size": fpath.stat().st_size})

    return {
        "status": "embedded",
        "agent_name": agent_name,
        "files": embedded,
        "count": len(embedded),
    }
