from __future__ import annotations
import datetime
import io
import os
import shutil
import tarfile
import time
from dataclasses import asdict
from pathlib import Path

import yaml
from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
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


@router.post("/api/backup")
async def create_backup(request: Request):
    """Create a downloadable backup of configuration and app data."""
    data_dir = request.app.state.config_path.parent
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in ["config.yaml", "installed.json", "hardware.json"]:
            path = data_dir / name
            if path.exists():
                tar.add(str(path), arcname=f"backup/{name}")
        catalog_dir = data_dir.parent / "app-catalog"
        if catalog_dir.exists():
            tar.add(str(catalog_dir), arcname="backup/app-catalog")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/gzip",
        headers={"Content-Disposition": f"attachment; filename=tinyagentos-backup-{int(time.time())}.tar.gz"},
    )


@router.post("/api/restore")
async def restore_backup(request: Request, file: UploadFile):
    """Restore configuration from a backup tarball."""
    data_dir = request.app.state.config_path.parent
    content = await file.read()
    buf = io.BytesIO(content)
    try:
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            for member in tar.getmembers():
                # Strip the leading "backup/" prefix when extracting
                if not member.name.startswith("backup/"):
                    continue
                relative = member.name[len("backup/"):]
                if not relative:
                    continue
                dest = data_dir / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                f = tar.extractfile(member)
                if f is not None:
                    dest.write_bytes(f.read())
    except tarfile.TarError as e:
        return JSONResponse({"error": f"Invalid backup file: {e}"}, status_code=400)
    # Reload config if config.yaml was restored
    config_path = request.app.state.config_path
    if config_path.exists():
        try:
            with open(config_path) as fh:
                data = yaml.safe_load(fh) or {}
            new_config = AppConfig(
                server=data.get("server", {}),
                backends=data.get("backends", []),
                qmd=data.get("qmd", {}),
                agents=data.get("agents", []),
                metrics=data.get("metrics", {}),
                config_path=config_path,
            )
            request.app.state.config = new_config
        except Exception:
            pass
    return {"status": "restored", "message": "Backup restored successfully"}


@router.get("/api/settings/update-check")
async def check_for_updates(request: Request):
    """Check if a newer version of TinyAgentOS is available on GitHub."""
    import asyncio
    proc = await asyncio.create_subprocess_exec(
        "git", "fetch", "--dry-run", "origin", "master",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        cwd=str(Path(__file__).parent.parent.parent),
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode() if stdout else ""
    has_updates = bool(output.strip())

    # Get current commit
    proc2 = await asyncio.create_subprocess_exec(
        "git", "log", "-1", "--format=%h %s",
        stdout=asyncio.subprocess.PIPE,
        cwd=str(Path(__file__).parent.parent.parent),
    )
    stdout2, _ = await proc2.communicate()
    current = stdout2.decode().strip() if stdout2 else "unknown"

    return {
        "has_updates": has_updates,
        "current_version": "0.1.0",
        "current_commit": current,
    }


@router.post("/api/settings/update")
async def apply_update(request: Request):
    """Pull latest TinyAgentOS code from GitHub and restart."""
    import asyncio
    project_dir = Path(__file__).parent.parent.parent

    # Git pull
    proc = await asyncio.create_subprocess_exec(
        "git", "pull", "--ff-only", "origin", "master",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        cwd=str(project_dir),
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode() if stdout else ""

    if proc.returncode != 0:
        return JSONResponse({"error": f"Update failed: {output}"}, status_code=500)

    # Pip install to pick up new deps
    venv_pip = project_dir / "venv" / "bin" / "pip"
    pip_cmd = str(venv_pip) if venv_pip.exists() else "pip"
    proc2 = await asyncio.create_subprocess_exec(
        pip_cmd, "install", "-e", ".", "-q",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        cwd=str(project_dir),
    )
    await proc2.communicate()

    # Notify
    if hasattr(request.app.state, "notifications") and request.app.state.notifications:
        await request.app.state.notifications.add(
            "System updated",
            f"TinyAgentOS updated successfully. Restart to apply changes.\n{output.strip()}",
            level="info", source="system",
        )

    return {
        "status": "updated",
        "output": output.strip(),
        "message": "Update pulled. Restart TinyAgentOS to apply changes.",
    }
