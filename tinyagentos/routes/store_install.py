from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/api/store/install-v2")
async def install_app(request: Request):
    body = await request.json()
    app_id = body.get("app_id", "")
    if not app_id:
        return JSONResponse({"error": "app_id required"}, status_code=400)
    store = request.app.state.installed_apps
    await store.install(app_id, body.get("version", ""), body.get("metadata"))
    return JSONResponse({"ok": True, "app_id": app_id, "status": "installed"})


@router.post("/api/store/uninstall-v2")
async def uninstall_app(request: Request):
    body = await request.json()
    app_id = body.get("app_id", "")
    if not app_id:
        return JSONResponse({"error": "app_id required"}, status_code=400)
    store = request.app.state.installed_apps
    removed = await store.uninstall(app_id)
    return JSONResponse({"ok": removed, "app_id": app_id, "status": "uninstalled" if removed else "not_installed"})


@router.get("/api/store/installed-v2")
async def list_installed(request: Request):
    store = request.app.state.installed_apps
    items = await store.list_installed()
    return JSONResponse({"installed": items})
