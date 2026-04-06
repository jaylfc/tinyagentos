from __future__ import annotations
import datetime
import io
import tarfile
import time
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
    models_bytes = _dir_size(models_dir)
    items.append({
        "label": "Models",
        "path": str(models_dir),
        "size": _format_size(models_bytes),
        "bytes": models_bytes,
    })

    # Data dir
    data_bytes = _dir_size(data_dir)
    items.append({
        "label": "Data",
        "path": str(data_dir),
        "size": _format_size(data_bytes),
        "bytes": data_bytes,
    })

    # App catalog
    catalog_dir = getattr(app.state, "registry", None)
    if catalog_dir and hasattr(catalog_dir, "catalog_dir"):
        cat_path = catalog_dir.catalog_dir
    else:
        cat_path = data_dir.parent / "app-catalog"
    cat_bytes = _dir_size(cat_path)
    items.append({
        "label": "App Catalog",
        "path": str(cat_path),
        "size": _format_size(cat_bytes),
        "bytes": cat_bytes,
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

    webhooks = config.webhooks if hasattr(config, "webhooks") else []

    return templates.TemplateResponse(request, "settings.html", {
        "active_page": "settings",
        "config_yaml": config_yaml,
        "last_saved": last_saved,
        "hardware": hardware,
        "storage": storage,
        "platform_settings": platform_settings,
        "webhooks": webhooks,
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
        webhooks=data.get("webhooks", []),
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


@router.get("/api/settings/llm-proxy")
async def llm_proxy_status(request: Request):
    """Return LLM proxy status for the settings page."""
    proxy = request.app.state.llm_proxy
    return {
        "running": proxy.is_running() if hasattr(proxy, "is_running") else False,
        "port": proxy.port if hasattr(proxy, "port") else 4000,
        "backends": len(request.app.state.config.backends),
    }


@router.post("/api/settings/test-backend")
async def test_backend_connection(request: Request):
    """Test connectivity to a backend URL."""
    from tinyagentos.backend_adapters import get_adapter
    body = await request.json()
    url = body.get("url", "")
    backend_type = body.get("type", "rkllama")
    if not url:
        return JSONResponse({"error": "URL required"}, status_code=400)
    try:
        adapter = get_adapter(backend_type)
        http_client = request.app.state.http_client
        result = await adapter.health(http_client, url)
        return {"reachable": result["status"] == "ok", "response_ms": result.get("response_ms", 0), "models": result.get("models", [])}
    except Exception as e:
        return {"reachable": False, "error": str(e)}


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
                rel_path = Path(relative)
                if rel_path.is_absolute() or ".." in rel_path.parts:
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
                webhooks=data.get("webhooks", []),
                config_path=config_path,
            )
            request.app.state.config = new_config
        except Exception:
            pass
    return {"status": "restored", "message": "Backup restored successfully"}


class WebhookAdd(BaseModel):
    url: str
    type: str = "generic"
    bot_token: str = ""
    chat_id: str = ""


@router.get("/api/settings/webhooks")
async def get_webhooks(request: Request):
    """Return configured webhooks."""
    config = request.app.state.config
    webhooks = config.webhooks if hasattr(config, "webhooks") else []
    return {"webhooks": webhooks}


@router.post("/api/settings/webhooks")
async def add_webhook(request: Request, body: WebhookAdd):
    """Add a webhook endpoint."""
    config = request.app.state.config
    if not hasattr(config, "webhooks"):
        config.webhooks = []
    wh = {"url": body.url, "type": body.type}
    if body.bot_token:
        wh["bot_token"] = body.bot_token
    if body.chat_id:
        wh["chat_id"] = body.chat_id
    config.webhooks.append(wh)
    await save_config_locked(config, request.app.state.config_path)
    # Update the notifier with new config
    from tinyagentos.webhook_notifier import WebhookNotifier
    notifier = WebhookNotifier(config.to_dict())
    request.app.state.webhook_notifier = notifier
    request.app.state.notifications.set_webhook_notifier(notifier)
    return {"status": "added", "webhooks": config.webhooks}


@router.delete("/api/settings/webhooks/{index}")
async def remove_webhook(request: Request, index: int):
    """Remove a webhook by index."""
    config = request.app.state.config
    webhooks = config.webhooks if hasattr(config, "webhooks") else []
    if index < 0 or index >= len(webhooks):
        return JSONResponse({"error": "Invalid webhook index"}, status_code=400)
    webhooks.pop(index)
    config.webhooks = webhooks
    await save_config_locked(config, request.app.state.config_path)
    from tinyagentos.webhook_notifier import WebhookNotifier
    notifier = WebhookNotifier(config.to_dict())
    request.app.state.webhook_notifier = notifier
    request.app.state.notifications.set_webhook_notifier(notifier)
    return {"status": "removed", "webhooks": config.webhooks}


@router.post("/api/settings/webhooks/test")
async def test_webhook(request: Request):
    """Send a test notification to a webhook URL."""
    body = await request.json()
    url = body.get("url", "")
    wh_type = body.get("type", "generic")
    if not url:
        return JSONResponse({"error": "URL required"}, status_code=400)
    from tinyagentos.webhook_notifier import WebhookNotifier
    test_wh = {"url": url, "type": wh_type}
    if body.get("bot_token"):
        test_wh["bot_token"] = body["bot_token"]
    if body.get("chat_id"):
        test_wh["chat_id"] = body["chat_id"]
    notifier = WebhookNotifier({"webhooks": [test_wh]})
    try:
        await notifier.notify("TinyAgentOS Test", "This is a test notification from TinyAgentOS.", "info")
        return {"status": "sent", "message": "Test notification sent"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


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
