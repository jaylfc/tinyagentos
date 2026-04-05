# tinyagentos/routes/images.py
from __future__ import annotations

import base64
import json
import random
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

router = APIRouter()

IMAGES_DIR_NAME = "images"


class GenerateRequest(BaseModel):
    prompt: str
    model: str = "lcm-dreamshaper-v7"
    size: str = "512x512"
    steps: int = 4
    seed: int | None = None
    guidance_scale: float = 7.5


def _images_dir(request: Request) -> Path:
    """Return the images directory, creating it if needed."""
    data_dir = getattr(request.app.state, "data_dir", None)
    if data_dir:
        d = Path(data_dir) / IMAGES_DIR_NAME
    else:
        # Fall back to project-level data/images
        d = Path(__file__).parent.parent.parent / "data" / IMAGES_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _get_image_backend(request: Request) -> tuple[str | None, str]:
    """Find an image generation backend. Returns (url, backend_type).

    Priority:
    1. Explicit ``image_backend_url`` in server config (standalone SD servers).
    2. Any configured backend of type rkllama or ollama (both expose
       ``/v1/images/generations``), ordered by the optional ``priority`` field.
    """
    config = request.app.state.config

    # Check for explicit image backend in config
    image_url = config.server.get("image_backend_url")
    if image_url:
        return image_url, "openai"

    # Try configured backends — rkllama and ollama both support /v1/images/generations
    for backend in sorted(config.backends, key=lambda b: b.get("priority", 99)):
        if backend.get("type") in ("rkllama", "ollama"):
            return backend["url"], backend["type"]

    return None, ""


def _list_images(images_dir: Path) -> list[dict]:
    """List generated images with metadata, newest first."""
    results = []
    for png in images_dir.glob("*.png"):
        meta_path = png.with_suffix(".json")
        metadata = {}
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        results.append({
            "filename": png.name,
            "path": f"/data/images/{png.name}",
            "size_bytes": png.stat().st_size,
            "prompt": metadata.get("prompt", ""),
            "model": metadata.get("model", ""),
            "size": metadata.get("size", ""),
            "steps": metadata.get("steps", 0),
            "seed": metadata.get("seed", 0),
            "guidance_scale": metadata.get("guidance_scale", 0),
        })
    results.sort(key=lambda x: x["filename"], reverse=True)
    return results


@router.get("/images", response_class=HTMLResponse)
async def images_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "images.html", {
        "active_page": "images",
    })


@router.post("/api/images/generate")
async def generate_image(request: Request, body: GenerateRequest):
    """Generate an image from a text prompt using any configured image backend."""
    backend_url, backend_type = _get_image_backend(request)
    if not backend_url:
        return JSONResponse(
            {"error": "No image generation backend configured. Add rkllama or ollama backend, or set image_backend_url in config."},
            status_code=503,
        )

    seed = body.seed if body.seed is not None else random.randint(0, 2**32 - 1)

    payload = {
        "prompt": body.prompt,
        "model": body.model,
        "size": body.size,
        "response_format": "b64_json",
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{backend_url.rstrip('/')}/v1/images/generations",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError:
        return JSONResponse(
            {"error": f"Cannot connect to image backend at {backend_url}. Is it running?"},
            status_code=503,
        )
    except httpx.TimeoutException:
        return JSONResponse(
            {"error": "Image generation timed out. The backend may be busy."},
            status_code=504,
        )
    except httpx.HTTPStatusError as e:
        return JSONResponse(
            {"error": f"Image backend returned error: {e.response.status_code}"},
            status_code=502,
        )
    except Exception as e:
        return JSONResponse(
            {"error": f"Unexpected error: {str(e)}"},
            status_code=500,
        )

    # Extract base64 image data from OpenAI-compatible response
    try:
        image_data = data["data"][0]["b64_json"]
    except (KeyError, IndexError):
        return JSONResponse(
            {"error": "Unexpected response format from image backend"},
            status_code=502,
        )

    # Decode and save
    images_dir = _images_dir(request)
    timestamp = int(time.time())
    filename = f"{timestamp}_{seed}.png"
    image_bytes = base64.b64decode(image_data)
    image_path = images_dir / filename
    image_path.write_bytes(image_bytes)

    # Save metadata sidecar
    metadata = {
        "prompt": body.prompt,
        "model": body.model,
        "size": body.size,
        "steps": body.steps,
        "seed": seed,
        "guidance_scale": body.guidance_scale,
    }
    meta_path = images_dir / f"{timestamp}_{seed}.json"
    meta_path.write_text(json.dumps(metadata, indent=2))

    return {
        "status": "generated",
        "filename": filename,
        "path": f"/data/images/{filename}",
        **metadata,
    }


@router.get("/api/images")
async def list_images(request: Request):
    """List all generated images with metadata, newest first."""
    images_dir = _images_dir(request)
    return {"images": _list_images(images_dir)}


@router.delete("/api/images/{filename}")
async def delete_image(request: Request, filename: str):
    """Delete a generated image and its metadata sidecar."""
    images_dir = _images_dir(request)

    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        return JSONResponse({"error": "Invalid filename"}, status_code=400)

    image_path = images_dir / filename
    if not image_path.exists():
        return JSONResponse({"error": f"Image '{filename}' not found"}, status_code=404)

    image_path.unlink()
    # Also delete metadata sidecar if it exists
    meta_path = image_path.with_suffix(".json")
    if meta_path.exists():
        meta_path.unlink()

    return {"status": "deleted", "filename": filename}
