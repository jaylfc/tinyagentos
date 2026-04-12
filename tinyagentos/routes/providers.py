from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from tinyagentos.backend_adapters import get_adapter
from tinyagentos.config import save_config_locked, VALID_BACKEND_TYPES

router = APIRouter()

class ProviderCreate(BaseModel):
    name: str
    type: str
    url: str
    priority: int = 99
    api_key_secret: str | None = None
    model: str = "default"

class ProviderTest(BaseModel):
    type: str
    url: str

@router.get("/api/providers")
async def list_providers(request: Request):
    """List all configured providers with live status."""
    config = request.app.state.config
    http_client = request.app.state.http_client
    providers = []
    for backend in config.backends:
        status = "unknown"
        response_ms = 0
        models = []
        try:
            adapter = get_adapter(backend["type"])
            result = await adapter.health(http_client, backend["url"])
            status = result.get("status", "error")
            response_ms = result.get("response_ms", 0)
            models = result.get("models", [])
        except Exception:
            status = "error"
        providers.append({
            **backend,
            "status": status,
            "response_ms": response_ms,
            "models": models,
        })
    return providers

@router.post("/api/providers/test")
async def test_provider(request: Request, body: ProviderTest):
    """Test connectivity to a provider before saving."""
    if not body.url:
        return JSONResponse({"error": "URL required"}, status_code=400)
    if body.type not in VALID_BACKEND_TYPES:
        return JSONResponse({"error": f"Invalid type. Must be one of: {sorted(VALID_BACKEND_TYPES)}"}, status_code=400)
    try:
        adapter = get_adapter(body.type)
        http_client = request.app.state.http_client
        result = await adapter.health(http_client, body.url)
        return {
            "reachable": result["status"] == "ok",
            "response_ms": result.get("response_ms", 0),
            "models": result.get("models", []),
        }
    except Exception as e:
        return {"reachable": False, "error": str(e)}

@router.post("/api/providers")
async def add_provider(request: Request, body: ProviderCreate):
    """Add a new provider to the configuration."""
    config = request.app.state.config
    if any(b["name"] == body.name for b in config.backends):
        return JSONResponse({"error": f"Provider '{body.name}' already exists"}, status_code=409)
    config.backends.append(body.model_dump(exclude_none=True))
    await save_config_locked(config, config.config_path)
    # Reconfigure LLM proxy if running
    proxy = getattr(request.app.state, "llm_proxy", None)
    if proxy and proxy.is_running():
        proxy.write_config(config.backends)
    return {"status": "added", "name": body.name}

@router.delete("/api/providers/{name}")
async def delete_provider(request: Request, name: str):
    """Remove a provider."""
    config = request.app.state.config
    config.backends = [b for b in config.backends if b.get("name") != name]
    await save_config_locked(config, config.config_path)
    return {"status": "deleted", "name": name}
