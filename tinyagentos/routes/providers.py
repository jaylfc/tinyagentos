from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from tinyagentos.backend_adapters import get_adapter
from tinyagentos.config import save_config_locked, VALID_BACKEND_TYPES

router = APIRouter()

# Provider categories used by the UI to group entries. The backend
# doesn't care about category for routing — it's purely display metadata.
CLOUD_TYPES = {"openai", "anthropic"}


def _categorise(provider: dict) -> str:
    """Return the UI category for a provider entry.

    - ``cloud`` for managed API providers (OpenAI, Anthropic, etc.)
    - ``network`` for backends reported by a remote cluster worker
    - ``local`` for controller-local configured backends
    """
    if provider.get("source", "").startswith("worker:"):
        return "network"
    if provider.get("type", "") in CLOUD_TYPES:
        return "cloud"
    return "local"


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
    """List every provider the controller knows about.

    Combines three sources into one unified list with a ``source`` and
    ``category`` tag on each entry:

    - **Controller-local** backends from ``config.backends`` — user adds
      these via the Add Provider form. Includes cloud providers (OpenAI,
      Anthropic) and on-host local backends (rkllama on the Pi, etc.).
    - **Worker-reported** backends from ``cluster.aggregate_catalog()``
      — any online worker's live backends (ollama on the Fedora worker,
      llama-cpp on a gaming PC, etc.). These aren't in the config; they
      appear automatically when the worker registers and heartbeats.

    The UI groups by ``category`` (local / network / cloud) and can show
    a worker host badge when ``category == "network"``.
    """
    config = request.app.state.config
    http_client = request.app.state.http_client
    providers = []

    # 1) Controller-local providers (live health probe)
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
        entry = {
            **backend,
            "status": status,
            "response_ms": response_ms,
            "models": models,
            "source": "local",
        }
        entry["category"] = _categorise(entry)
        providers.append(entry)

    # 2) Worker-reported remote backends (from heartbeats — no extra
    #    probe, the worker already vouches for their status).
    cluster = getattr(request.app.state, "cluster_manager", None)
    if cluster is not None:
        try:
            agg = cluster.aggregate_catalog()
            for b in agg.get("backends", []):
                worker_name = b.get("worker", "")
                entry = {
                    # Prefix the name with worker for uniqueness across cluster
                    "name": f"{worker_name}/{b.get('name', 'backend')}",
                    "type": b.get("type", ""),
                    "url": b.get("url", ""),
                    "priority": b.get("priority", 99),
                    "status": b.get("status", "online"),
                    "response_ms": b.get("response_ms", 0),
                    "models": b.get("models", []),
                    "source": f"worker:{worker_name}",
                    "worker_name": worker_name,
                    "worker_url": b.get("worker_url", ""),
                    "worker_platform": b.get("worker_platform", ""),
                }
                entry["category"] = _categorise(entry)
                providers.append(entry)
        except Exception:
            # Cluster manager not ready or misbehaving — don't fail the
            # whole endpoint, just skip remote backends.
            pass

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
    """Add a new provider to the configuration.

    Only controller-local providers can be added this way (cloud APIs
    and custom on-host / network endpoints). Worker-reported backends
    auto-populate from heartbeats and don't need to be added manually.
    """
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
    """Remove a provider. Only local (config-based) providers can be
    deleted — worker-reported backends disappear when the worker goes
    offline."""
    config = request.app.state.config
    # Prevent accidental deletion of worker-prefixed names
    if "/" in name:
        return JSONResponse(
            {"error": "Cluster worker backends are auto-discovered and cannot be deleted here. Deregister the worker instead."},
            status_code=400,
        )
    config.backends = [b for b in config.backends if b.get("name") != name]
    await save_config_locked(config, config.config_path)
    return {"status": "deleted", "name": name}
