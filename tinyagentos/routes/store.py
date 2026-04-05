# tinyagentos/routes/store.py
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from tinyagentos.installers.base import get_installer


class InstallRequest(BaseModel):
    app_id: str
    variant_id: str | None = None  # for models


class UninstallRequest(BaseModel):
    app_id: str

router = APIRouter()


def _build_app_items(registry, profile_id: str, type_filter: str | None = None, query: str | None = None):
    """Build app item dicts for templates, with compat info and optional filtering."""
    apps = registry.list_available(type_filter=type_filter or None)
    installed_ids = {a["id"] for a in registry.list_installed()}
    items = []
    for a in apps:
        if query and query.lower() not in a.name.lower() and query.lower() not in a.description.lower():
            continue
        # Determine hardware compatibility
        compat = None
        if a.hardware_tiers:
            tier = a.hardware_tiers.get(profile_id)
            if tier is None:
                compat = "unsupported"
            elif isinstance(tier, str) and tier == "unsupported":
                compat = "unsupported"
            elif isinstance(tier, str) and tier in ("full", "optimal"):
                compat = "compatible"
            elif isinstance(tier, dict):
                compat = "compatible"
            else:
                compat = "degraded"
        items.append({"manifest": a, "installed": a.id in installed_ids, "compat": compat})
    return items


@router.get("/store", response_class=HTMLResponse)
async def store_page(request: Request):
    templates = request.app.state.templates
    registry = request.app.state.registry
    profile_id = request.app.state.hardware_profile.profile_id
    items = _build_app_items(registry, profile_id)
    installed_apps = [i for i in items if i["installed"]]
    return templates.TemplateResponse("store.html", {
        "request": request,
        "active_page": "store",
        "apps": items,
        "installed_apps": installed_apps,
    })


@router.get("/api/partials/app-grid", response_class=HTMLResponse)
async def app_grid_partial(request: Request, type: str | None = None, q: str | None = None):
    templates = request.app.state.templates
    registry = request.app.state.registry
    profile_id = request.app.state.hardware_profile.profile_id
    items = _build_app_items(registry, profile_id, type_filter=type, query=q)
    return templates.TemplateResponse("partials/app_grid.html", {
        "request": request,
        "apps": items,
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


@router.post("/api/store/sync")
async def sync_store(request: Request):
    from tinyagentos.catalog_sync import sync_catalog
    registry = request.app.state.registry
    result = await sync_catalog(registry.catalog_dir)
    if result["success"]:
        registry.reload()
    return result


@router.post("/api/store/install")
async def install_app(request: Request, body: InstallRequest):
    registry = request.app.state.registry
    manifest = registry.get(body.app_id)
    if not manifest:
        return JSONResponse({"error": f"App '{body.app_id}' not found"}, status_code=404)
    if registry.is_installed(body.app_id):
        return JSONResponse({"error": f"App '{body.app_id}' already installed"}, status_code=409)

    method = manifest.install.get("method", "")
    try:
        installer = get_installer(method)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    kwargs = {}
    if manifest.type == "model" and body.variant_id:
        variant = next((v for v in manifest.variants if v["id"] == body.variant_id), None)
        if not variant:
            return JSONResponse({"error": f"Variant '{body.variant_id}' not found"}, status_code=404)
        kwargs["variant"] = variant

    result = await installer.install(body.app_id, manifest.install, **kwargs)
    if result["success"]:
        registry.mark_installed(body.app_id, manifest.version)
        return {"status": "installed", "app_id": body.app_id}
    return JSONResponse({"error": result.get("error", "Install failed")}, status_code=500)


@router.post("/api/store/uninstall")
async def uninstall_app(request: Request, body: UninstallRequest):
    registry = request.app.state.registry
    if not registry.is_installed(body.app_id):
        return JSONResponse({"error": f"App '{body.app_id}' not installed"}, status_code=404)

    manifest = registry.get(body.app_id)
    method = manifest.install.get("method", "") if manifest else "pip"
    try:
        installer = get_installer(method)
    except ValueError:
        pass  # best effort uninstall
    else:
        await installer.uninstall(body.app_id)

    registry.mark_uninstalled(body.app_id)
    return {"status": "uninstalled", "app_id": body.app_id}
