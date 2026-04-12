from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from tinyagentos.agent_templates import (
    list_templates, get_template, CATEGORIES, EXTERNAL_SOURCES,
    fetch_external_index, fetch_external_template, template_stats,
)

router = APIRouter()


@router.get("/api/templates/stats")
async def api_template_stats():
    """Return template count stats."""
    return template_stats()


@router.get("/api/templates")
async def api_list_templates(category: str | None = None, source: str | None = None,
                             limit: int = 50, offset: int = 0):
    """List agent templates with filtering and pagination.

    source: "builtin", "awesome-openclaw-agents", "system-prompt-library", or omit for all.
    """
    all_templates = list_templates(category=category, source=source)
    total = len(all_templates)
    page = all_templates[offset:offset + limit]
    # Strip system_prompt from list view to reduce payload
    compact = [
        {k: v for k, v in t.items() if k != "system_prompt"}
        for t in page
    ]
    return {"templates": compact, "total": total, "categories": CATEGORIES}


@router.get("/api/templates/sources")
async def list_template_sources():
    """List available external template sources."""
    return {"sources": EXTERNAL_SOURCES}


@router.get("/api/templates/external/{source_id}")
async def list_external_templates(request: Request, source_id: str):
    """Fetch template index from an external source."""
    http_client = request.app.state.http_client
    templates = await fetch_external_index(source_id, http_client)
    return {"source": source_id, "templates": templates, "count": len(templates)}


@router.get("/api/templates/external/{source_id}/fetch")
async def fetch_external(request: Request, source_id: str, path: str = ""):
    """Fetch a single template's full content from an external source."""
    if not path:
        return JSONResponse({"error": "path parameter required"}, status_code=400)
    http_client = request.app.state.http_client
    template = await fetch_external_template(source_id, path, http_client)
    if not template:
        return JSONResponse({"error": "Template not found or source unavailable"}, status_code=404)
    return template


@router.get("/api/templates/{template_id}")
async def api_get_template(template_id: str):
    """Get a single template by ID."""
    tmpl = get_template(template_id)
    if not tmpl:
        return JSONResponse({"error": "Template not found"}, status_code=404)
    return tmpl
