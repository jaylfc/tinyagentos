# tinyagentos/routes/models.py
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel


class DownloadRequest(BaseModel):
    app_id: str
    variant_id: str


class DeleteRequest(BaseModel):
    app_id: str


router = APIRouter()

DEFAULT_MODELS_DIR = Path("/opt/tinyagentos/models")


def get_downloaded_models(models_dir: Path) -> list[dict]:
    """Scan models directory and return list of downloaded model files."""
    if not models_dir.exists():
        return []
    results = []
    for f in sorted(models_dir.glob("*")):
        if f.is_file() and f.suffix in (".gguf", ".rkllm", ".bin"):
            results.append({
                "filename": f.name,
                "size_mb": f.stat().st_size // (1024 * 1024),
                "format": f.suffix.lstrip("."),
                "path": str(f),
            })
    return results


def _models_dir(request: Request) -> Path:
    return getattr(request.app.state, "models_dir", DEFAULT_MODELS_DIR)


def _variant_compatibility(variant: dict, hardware_profile) -> str:
    """Return green/yellow/red based on hardware compatibility."""
    ram_mb = hardware_profile.ram_mb
    min_ram = variant.get("min_ram_mb", 0)
    requires_npu = variant.get("requires_npu", [])

    # Check NPU requirement
    if requires_npu:
        soc = hardware_profile.cpu.soc
        if soc in requires_npu:
            return "green"
        else:
            return "red"

    # Check RAM
    if min_ram == 0:
        return "green"
    if ram_mb >= min_ram * 1.5:
        return "green"
    elif ram_mb >= min_ram:
        return "yellow"
    else:
        return "red"


def _model_to_dict(manifest, hardware_profile, downloaded_files: list[dict]) -> dict:
    """Convert an AppManifest to a model dict with compatibility info."""
    downloaded_filenames = {d["filename"] for d in downloaded_files}

    variants = []
    for v in manifest.variants:
        expected_filename = f"{manifest.id}-{v['id']}.{v.get('format', 'bin')}"
        is_downloaded = expected_filename in downloaded_filenames
        compat = _variant_compatibility(v, hardware_profile)
        variants.append({
            **v,
            "downloaded": is_downloaded,
            "compatibility": compat,
        })

    # Overall compatibility: best variant compatibility
    compat_order = {"green": 0, "yellow": 1, "red": 2}
    best = min((v["compatibility"] for v in variants), key=lambda c: compat_order.get(c, 2)) if variants else "red"

    return {
        "id": manifest.id,
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
        "capabilities": manifest.capabilities,
        "hardware_tiers": manifest.hardware_tiers,
        "variants": variants,
        "compatibility": best,
        "has_downloaded_variant": any(v["downloaded"] for v in variants),
    }


@router.get("/models", response_class=HTMLResponse)
async def models_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "models.html", {
        "active_page": "models",
    })


@router.get("/api/models")
async def list_models(request: Request):
    """List all available models with download status and compatibility."""
    registry = request.app.state.registry
    hardware_profile = request.app.state.hardware_profile
    models_dir = _models_dir(request)

    models = registry.list_available(type_filter="model")
    downloaded = get_downloaded_models(models_dir)

    return {
        "models": [_model_to_dict(m, hardware_profile, downloaded) for m in models],
        "downloaded_files": downloaded,
        "hardware_profile_id": hardware_profile.profile_id,
    }


@router.get("/api/models/{model_id}")
async def get_model(request: Request, model_id: str):
    """Get detailed information about a specific model."""
    registry = request.app.state.registry
    hardware_profile = request.app.state.hardware_profile
    models_dir = _models_dir(request)

    manifest = registry.get(model_id)
    if not manifest or manifest.type != "model":
        return JSONResponse({"error": f"Model '{model_id}' not found"}, status_code=404)

    downloaded = get_downloaded_models(models_dir)
    return _model_to_dict(manifest, hardware_profile, downloaded)


@router.post("/api/models/download")
async def download_model(request: Request, body: DownloadRequest):
    """Start a background download for a specific model variant."""
    registry = request.app.state.registry
    manifest = registry.get(body.app_id)
    if not manifest or manifest.type != "model":
        return JSONResponse({"error": f"Model '{body.app_id}' not found"}, status_code=404)

    variant = next((v for v in manifest.variants if v["id"] == body.variant_id), None)
    if not variant:
        return JSONResponse({"error": f"Variant '{body.variant_id}' not found"}, status_code=404)

    url = variant.get("download_url", "")
    if not url:
        return JSONResponse({"error": "No download URL for variant"}, status_code=400)

    models_dir = _models_dir(request)
    fmt = variant.get("format", "bin")
    filename = f"{body.app_id}-{body.variant_id}.{fmt}"
    dest = models_dir / filename

    download_id = f"{body.app_id}-{body.variant_id}"
    dm = request.app.state.download_manager
    dm.start_download(
        download_id=download_id,
        url=url,
        dest=dest,
        expected_sha256=variant.get("sha256"),
    )

    return {
        "status": "started",
        "download_id": download_id,
        "app_id": body.app_id,
        "variant_id": body.variant_id,
    }


@router.get("/api/models/downloads")
async def list_downloads(request: Request):
    """List all downloads with progress information."""
    dm = request.app.state.download_manager
    tasks = dm.list_all()
    return {
        "downloads": [_task_to_dict(t) for t in tasks],
    }


@router.get("/api/models/downloads/{download_id}")
async def get_download_progress(request: Request, download_id: str):
    """Get progress for a specific download."""
    dm = request.app.state.download_manager
    task = dm.get_progress(download_id)
    if not task:
        return JSONResponse({"error": f"Download '{download_id}' not found"}, status_code=404)
    return _task_to_dict(task)


def _task_to_dict(task) -> dict:
    pct = 0
    if task.total_bytes > 0:
        pct = round(task.downloaded_bytes / task.total_bytes * 100, 1)
    return {
        "id": task.id,
        "url": task.url,
        "dest": str(task.dest),
        "total_bytes": task.total_bytes,
        "downloaded_bytes": task.downloaded_bytes,
        "percent": pct,
        "status": task.status,
        "error": task.error,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
    }


@router.delete("/api/models/{model_id}")
async def delete_model(request: Request, model_id: str):
    """Delete all downloaded files for a model."""
    registry = request.app.state.registry
    models_dir = _models_dir(request)

    manifest = registry.get(model_id)
    if not manifest or manifest.type != "model":
        return JSONResponse({"error": f"Model '{model_id}' not found"}, status_code=404)

    deleted = []
    for f in models_dir.glob(f"{model_id}*"):
        if f.is_file() and f.suffix in (".gguf", ".rkllm", ".bin"):
            f.unlink()
            deleted.append(f.name)

    if deleted:
        registry.mark_uninstalled(model_id)

    return {"status": "deleted", "model_id": model_id, "deleted_files": deleted}
