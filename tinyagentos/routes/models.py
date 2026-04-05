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
    registry = request.app.state.registry
    manifest = registry.get(body.app_id)
    if not manifest or manifest.type != "model":
        return JSONResponse({"error": f"Model '{body.app_id}' not found"}, status_code=404)

    variant = next((v for v in manifest.variants if v["id"] == body.variant_id), None)
    if not variant:
        return JSONResponse({"error": f"Variant '{body.variant_id}' not found"}, status_code=404)

    from tinyagentos.installers.base import get_installer
    try:
        installer = get_installer(manifest.install.get("method", "download"))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    models_dir = _models_dir(request)
    if hasattr(installer, "models_dir"):
        installer.models_dir = models_dir

    result = await installer.install(body.app_id, manifest.install, variant=variant)
    if result["success"]:
        registry.mark_installed(body.app_id, manifest.version)
        return {"status": "downloaded", "app_id": body.app_id, "variant_id": body.variant_id, "path": result.get("path")}
    return JSONResponse({"error": result.get("error", "Download failed")}, status_code=500)


@router.delete("/api/models/{model_id}")
async def delete_model(request: Request, model_id: str):
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
