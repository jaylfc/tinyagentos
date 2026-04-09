from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path

router = APIRouter()

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
SPA_DIR = PROJECT_DIR / "static" / "desktop"


@router.get("/api/desktop/settings")
async def get_settings(request: Request):
    store = request.app.state.desktop_settings
    settings = await store.get_settings("user")
    return JSONResponse(settings)


@router.put("/api/desktop/settings")
async def update_settings(request: Request):
    store = request.app.state.desktop_settings
    body = await request.json()
    await store.update_settings("user", body)
    return JSONResponse({"ok": True})


@router.get("/api/desktop/dock")
async def get_dock(request: Request):
    store = request.app.state.desktop_settings
    dock = await store.get_dock("user")
    return JSONResponse(dock)


@router.put("/api/desktop/dock")
async def update_dock(request: Request):
    store = request.app.state.desktop_settings
    body = await request.json()
    await store.update_dock("user", body)
    return JSONResponse({"ok": True})


@router.get("/api/desktop/windows")
async def get_windows(request: Request):
    store = request.app.state.desktop_settings
    windows = await store.get_windows("user")
    return JSONResponse(windows)


@router.put("/api/desktop/windows")
async def save_windows(request: Request):
    store = request.app.state.desktop_settings
    body = await request.json()
    await store.save_windows("user", body.get("positions", []))
    return JSONResponse({"ok": True})


@router.get("/desktop/{rest:path}")
async def serve_spa(rest: str = ""):
    index = SPA_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"error": "Desktop shell not built. Run: cd desktop && npm run build"}, status_code=404)
