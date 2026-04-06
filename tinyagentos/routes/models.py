# tinyagentos/routes/models.py
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from tinyagentos.model_sources import (
    estimate_ram_mb,
    get_compatibility,
    get_huggingface_model_files,
    search_huggingface,
    search_ollama,
)

logger = logging.getLogger(__name__)


class DownloadRequest(BaseModel):
    app_id: str
    variant_id: str


class DeleteRequest(BaseModel):
    app_id: str


class PullRequest(BaseModel):
    model_name: str


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


def _add_compatibility_to_results(results: list[dict], hardware_profile) -> list[dict]:
    """Add hardware compatibility info to search results."""
    ram_mb = hardware_profile.ram_mb
    for r in results:
        if r.get("source") == "huggingface":
            r["ram_available_mb"] = ram_mb
        elif r.get("source") == "ollama":
            r["ram_available_mb"] = ram_mb
    return results


def _search_catalog(registry, query: str, hardware_profile) -> list[dict]:
    """Search the local catalog for models matching the query."""
    query_lower = query.lower()
    models = registry.list_available(type_filter="model")
    results = []
    for m in models:
        if query_lower in m.name.lower() or query_lower in m.id.lower() or query_lower in m.description.lower():
            results.append({
                "id": m.id,
                "name": m.name,
                "author": "catalog",
                "description": m.description,
                "tags": m.capabilities,
                "source": "catalog",
                "url": f"/api/models/{m.id}",
            })
    return results


def _render_search_results(request: Request, results: list[dict], source: str):
    """Render search results as HTML partial or JSON based on Accept header."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        templates = request.app.state.templates
        return templates.TemplateResponse(
            request,
            "partials/model_search_results.html",
            {"results": results, "source": source},
        )
    return {"results": results, "source": source, "count": len(results)}


@router.get("/api/models/search/huggingface")
async def search_hf(request: Request, q: str = Query("", min_length=0)):
    """Search HuggingFace for GGUF models."""
    if not q.strip():
        return {"results": [], "source": "huggingface"}
    hardware_profile = request.app.state.hardware_profile
    results = await search_huggingface(q.strip())
    results = _add_compatibility_to_results(results, hardware_profile)
    return {"results": results, "source": "huggingface"}


@router.get("/api/models/search/ollama")
async def search_ol(request: Request, q: str = Query("", min_length=0)):
    """Search Ollama model library."""
    if not q.strip():
        return {"results": [], "source": "ollama"}
    hardware_profile = request.app.state.hardware_profile
    results = await search_ollama(q.strip())
    results = _add_compatibility_to_results(results, hardware_profile)
    return {"results": results, "source": "ollama"}


@router.get("/api/models/search")
async def search_models(
    request: Request,
    q: str = Query("", min_length=0),
    source: str = Query("all"),
):
    """Search models across sources. source=all|huggingface|ollama|catalog."""
    query = q.strip()
    if not query:
        return _render_search_results(request, [], source)

    hardware_profile = request.app.state.hardware_profile
    results: list[dict] = []

    if source in ("all", "huggingface"):
        hf_task = search_huggingface(query)
    else:
        hf_task = None

    if source in ("all", "ollama"):
        ol_task = search_ollama(query)
    else:
        ol_task = None

    if source in ("all", "catalog"):
        registry = request.app.state.registry
        catalog_results = _search_catalog(registry, query, hardware_profile)
    else:
        catalog_results = []

    # Await external searches concurrently
    tasks = []
    task_labels = []
    if hf_task:
        tasks.append(hf_task)
        task_labels.append("huggingface")
    if ol_task:
        tasks.append(ol_task)
        task_labels.append("ollama")

    if tasks:
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for label, result in zip(task_labels, gathered):
            if isinstance(result, Exception):
                logger.warning(f"Search {label} failed: {result}")
            elif isinstance(result, list):
                results.extend(result)

    results.extend(catalog_results)
    results = _add_compatibility_to_results(results, hardware_profile)

    return _render_search_results(request, results, source)


@router.get("/api/models/files/{model_id:path}")
async def get_model_files(request: Request, model_id: str):
    """Get GGUF files for a HuggingFace model with compatibility info."""
    hardware_profile = request.app.state.hardware_profile
    ram_mb = hardware_profile.ram_mb
    files = await get_huggingface_model_files(model_id)
    for f in files:
        ram_needed = estimate_ram_mb(f["size_mb"])
        f["ram_estimate_mb"] = ram_needed
        f["compatibility"] = get_compatibility(ram_needed, ram_mb)
    return {"model_id": model_id, "files": files, "ram_available_mb": ram_mb}


@router.post("/api/models/pull")
async def pull_model(request: Request, body: PullRequest):
    """Pull an Ollama model by calling the configured backend."""
    model_name = body.model_name.strip()
    if not model_name:
        return JSONResponse({"error": "model_name is required"}, status_code=400)
    try:
        http_client = request.app.state.http_client
        config = request.app.state.config
        ollama_url = None
        for b in config.backends:
            if b.type == "ollama":
                ollama_url = b.url
                break
        if not ollama_url:
            ollama_url = "http://localhost:11434"
        resp = await http_client.post(
            f"{ollama_url}/api/pull",
            json={"name": model_name, "stream": False},
            timeout=300,
        )
        if resp.status_code == 200:
            return {"status": "pulled", "model": model_name}
        return JSONResponse(
            {"error": f"Ollama pull failed: {resp.text}"},
            status_code=resp.status_code,
        )
    except Exception as e:
        logger.warning(f"Ollama pull failed: {e}")
        return JSONResponse({"error": str(e)}, status_code=502)


@router.get("/api/models/recommended")
async def recommended_models(request: Request):
    """Return models recommended for the current hardware profile."""
    registry = request.app.state.registry
    hw = request.app.state.hardware_profile
    profile_id = hw.profile_id

    all_models = registry.list_available(type_filter="model")
    recommended = []
    compatible = []

    for model in all_models:
        tiers = getattr(model, "hardware_tiers", {}) or {}
        tier_status = tiers.get(profile_id, "")

        entry = {
            "id": model.id,
            "name": model.name,
            "description": getattr(model, "description", ""),
            "compatibility": tier_status or "unknown",
        }

        if tier_status == "full":
            recommended.append(entry)
        elif tier_status == "limited":
            compatible.append(entry)

    return {
        "profile_id": profile_id,
        "recommended": recommended,
        "compatible": compatible,
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
