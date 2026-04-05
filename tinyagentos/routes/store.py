# tinyagentos/routes/store.py
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()


@router.get("/store", response_class=HTMLResponse)
async def store_page(request: Request):
    templates = request.app.state.templates
    registry = request.app.state.registry
    apps = registry.list_available()
    installed_ids = {a["id"] for a in registry.list_installed()}
    return templates.TemplateResponse("store.html", {
        "request": request,
        "active_page": "store",
        "apps": [{"manifest": a, "installed": a.id in installed_ids} for a in apps],
    })


@router.get("/api/store/catalog")
async def list_catalog(request: Request, type: str | None = None):
    registry = request.app.state.registry
    apps = registry.list_available(type_filter=type)
    return [
        {
            "id": a.id, "name": a.name, "type": a.type, "version": a.version,
            "description": a.description, "icon": a.icon,
            "requires": a.requires, "hardware_tiers": a.hardware_tiers,
            "installed": registry.is_installed(a.id),
        }
        for a in apps
    ]


@router.get("/api/store/installed")
async def list_installed(request: Request):
    return request.app.state.registry.list_installed()


@router.get("/api/store/app/{app_id}")
async def get_app(request: Request, app_id: str):
    registry = request.app.state.registry
    app = registry.get(app_id)
    if not app:
        return JSONResponse({"error": f"App '{app_id}' not found"}, status_code=404)
    return {
        "id": app.id, "name": app.name, "type": app.type, "version": app.version,
        "description": app.description, "homepage": app.homepage, "license": app.license,
        "requires": app.requires, "install": app.install,
        "hardware_tiers": app.hardware_tiers, "config_schema": app.config_schema,
        "variants": app.variants, "capabilities": app.capabilities,
        "installed": registry.is_installed(app.id),
    }


@router.get("/api/hardware")
async def hardware_profile(request: Request):
    profile = request.app.state.hardware_profile
    data = asdict(profile)
    data["profile_id"] = profile.profile_id
    return data


@router.post("/api/hardware/detect")
async def redetect_hardware(request: Request):
    from tinyagentos.hardware import detect_hardware
    profile = detect_hardware()
    profile.save(request.app.state.config_path.parent / "hardware.json")
    request.app.state.hardware_profile = profile
    data = asdict(profile)
    data["profile_id"] = profile.profile_id
    return data
