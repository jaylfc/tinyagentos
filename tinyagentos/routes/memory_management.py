"""Memory Management Routes — taOSmd backend integration.

Exposes stats, settings, backend capabilities/schema, and per-agent
memory config. All routes instantiate TaOSmdBackend with auto-init
so the settings DB is created on first access without a separate
startup step.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_SETTINGS_DB = "data/memory-settings.db"


def _backend(request: Request):
    """Return a TaOSmdBackend wired to app-state stores where available."""
    from taosmd import TaOSmdBackend

    data_dir: Path = getattr(request.app.state, "data_dir", Path("data"))
    settings_db_path = data_dir / "memory-settings.db"

    kg = getattr(request.app.state, "knowledge_graph", None)
    archive = getattr(request.app.state, "archive", None)

    return TaOSmdBackend(
        kg=kg,
        archive=archive,
        settings_db_path=settings_db_path,
    )


# --- Memory Management Routes ---

@router.get("/api/memory/stats")
async def memory_stats(request: Request):
    """Return aggregated stats from all memory stores."""
    try:
        b = _backend(request)
        stats = await b.get_stats()
        return stats
    except Exception as exc:
        logger.warning("memory stats failed: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/memory/settings")
async def memory_settings_get(request: Request):
    """Return current memory settings."""
    try:
        b = _backend(request)
        settings = await b.get_settings()
        return settings
    except Exception as exc:
        logger.warning("memory settings get failed: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.put("/api/memory/settings")
async def memory_settings_put(request: Request):
    """Update memory settings from JSON body; returns merged settings."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    try:
        b = _backend(request)
        updated = await b.update_settings(body)
        return updated
    except Exception as exc:
        logger.warning("memory settings update failed: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/memory/backend/capabilities")
async def memory_backend_capabilities(request: Request):
    """Return backend name, version, and capabilities list."""
    try:
        from taosmd import TaOSmdBackend
        return {
            "name": TaOSmdBackend.name,
            "version": TaOSmdBackend.version,
            "capabilities": TaOSmdBackend.capabilities,
        }
    except Exception as exc:
        logger.warning("memory backend capabilities failed: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/memory/backend/settings-schema")
async def memory_backend_settings_schema(request: Request):
    """Return JSON Schema for the memory settings form."""
    try:
        b = _backend(request)
        schema = await b.get_settings_schema()
        return schema
    except Exception as exc:
        logger.warning("memory settings schema failed: %s", exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.get("/api/agents/{name}/memory-config")
async def agent_memory_config_get(request: Request, name: str):
    """Return the memory config for a specific agent."""
    try:
        b = _backend(request)
        config = await b.get_agent_config(name)
        return config
    except Exception as exc:
        logger.warning("agent memory config get failed for %s: %s", name, exc)
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.put("/api/agents/{name}/memory-config")
async def agent_memory_config_put(request: Request, name: str):
    """Update a specific agent's memory config from JSON body."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    try:
        b = _backend(request)
        updated = await b.update_agent_config(name, body)
        return updated
    except Exception as exc:
        logger.warning("agent memory config update failed for %s: %s", name, exc)
        return JSONResponse({"error": str(exc)}, status_code=500)
