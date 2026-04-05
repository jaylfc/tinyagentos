from __future__ import annotations
import datetime
import os
import shutil
from dataclasses import asdict
from pathlib import Path

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from tinyagentos.config import AppConfig, save_config_locked, validate_config

router = APIRouter()


class ConfigUpdate(BaseModel):
    yaml: str


class PlatformUpdate(BaseModel):
    poll_interval: int
    retention_days: int
    catalog_repo: str = ""


def _dir_size(path: Path) -> int:
    """Return total size of a directory in bytes."""
    if not path.exists():
        return 0
    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _format_size(size_bytes: int) -> str:
    """Format bytes into a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"


def _get_storage_stats(app) -> list[dict]:
    """Compute storage usage for key directories."""
    data_dir = app.state.config_path.parent
    items = []

    # Models dir
    models_dir = data_dir / "models"
    items.append({
        "label": "Models",
        "path": str(models_dir),
        "size": _format_size(_dir_size(models_dir)),
        "bytes": _dir_size(models_dir),
    })

    # Data dir
    items.append({
        "label": "Data",
        "path": str(data_dir),
        "size": _format_size(_dir_size(data_dir)),
        "bytes": _dir_size(data_dir),
    })

    # App catalog
    catalog_dir = getattr(app.state, "registry", None)
    if catalog_dir and hasattr(catalog_dir, "catalog_dir"):
        cat_path = catalog_dir.catalog_dir
    else:
        cat_path = data_dir.parent / "app-catalog"
    items.append({
        "label": "App Catalog",
        "path": str(cat_path),
        "size": _format_size(_dir_size(cat_path)),
        "bytes": _dir_size(cat_path),
    })

    return items


@router.get("/settings", response_class=HTMLResponse)
@router.get("/config", response_class=HTMLResponse)
async def settings_page(request: Request):
    config = request.app.state.config
    templates = request.app.state.templates
    config_yaml = yaml.dump(config.to_dict(), default_flow_style=False, sort_keys=False)
    config_path = request.app.state.config_path
    last_saved = None
    if config_path.exists():
        mtime = config_path.stat().st_mtime
        last_saved = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

    hardware = request.app.state.hardware_profile
    storage = _get_storage_stats(request.app)

    platform_settings = {
        "catalog_repo": "",
        "poll_interval": config.metrics.get("poll_interval", 30),
        "retention_days": config.metrics.get("retention_days", 30),
    }

    return templates.TemplateResponse(request, "settings.html", {
        "active_page": "settings",
        "config_yaml": config_yaml,
        "last_saved": last_saved,
        "hardware": hardware,
        "storage": storage,
        "platform_settings": platform_settings,
    })


@router.get("/api/config")
async def get_config(request: Request):
    """Get current configuration as YAML."""
    config = request.app.state.config
    return {"yaml": yaml.dump(config.to_dict(), default_flow_style=False, sort_keys=False)}


@router.put("/api/config")
async def save_config_endpoint(request: Request, body: ConfigUpdate, validate_only: bool = False):
    """Validate and save configuration from YAML."""
    try:
        data = yaml.safe_load(body.yaml)
    except yaml.YAMLError as e:
        return JSONResponse({"error": f"Invalid YAML: {e}"}, status_code=400)
    if not isinstance(data, dict):
        return JSONResponse({"error": "Config must be a YAML mapping"}, status_code=400)
    new_config = AppConfig(
        server=data.get("server", {}),
        backends=data.get("backends", []),
        qmd=data.get("qmd", {}),
        agents=data.get("agents", []),
        metrics=data.get("metrics", {}),
        config_path=request.app.state.config_path,
    )
    errors = validate_config(new_config)
    if errors:
        return JSONResponse({"error": "Validation failed", "details": errors}, status_code=400)
    if validate_only:
        return {"status": "valid", "message": "Config is valid"}
    await save_config_locked(new_config, request.app.state.config_path)
    request.app.state.config = new_config
    return {"status": "saved", "message": "Config saved successfully"}


@router.get("/api/settings/storage")
async def get_storage(request: Request):
    """Return storage usage as JSON."""
    storage = _get_storage_stats(request.app)
    return {"storage": storage}


@router.put("/api/settings/platform")
async def save_platform_settings(request: Request, body: PlatformUpdate):
    """Update platform settings (metrics interval/retention)."""
    config = request.app.state.config
    config.metrics["poll_interval"] = body.poll_interval
    config.metrics["retention_days"] = body.retention_days
    await save_config_locked(config, request.app.state.config_path)
    return {"status": "saved", "message": "Platform settings saved"}
