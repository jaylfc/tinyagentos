from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)

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

    # Look up the agent's qmd_url from config
    config = request.app.state.config
    agent_dict = next((a for a in config.agents if a.get("name") == agent_name), None)
    qmd_url = agent_dict.get("qmd_url") if agent_dict else None

    http_client = request.app.state.http_client
    embedded_files = []
    all_embedded = True

    for fname in filenames:
        fpath = UPLOAD_DIR / fname
        text = fpath.read_text(errors="replace")
        file_embedded = False

        if qmd_url:
            try:
                resp = await http_client.post(
                    qmd_url.rstrip("/") + "/api/embed",
                    json={"text": text, "collection": "imports"},
                    timeout=30.0,
                )
                resp.raise_for_status()
                file_embedded = True
            except Exception as exc:
                logger.warning(
                    "QMD embed failed for agent %s file %s (%s): %s",
                    agent_name, fname, qmd_url, exc,
                )
                all_embedded = False
        else:
            all_embedded = False

        embedded_files.append({
            "filename": fname,
            "size": fpath.stat().st_size,
            "embedded": file_embedded,
        })

    return {
        "status": "embedded",
        "agent_name": agent_name,
        "files": embedded_files,
        "count": len(embedded_files),
        "embedded": all_embedded,
    }
