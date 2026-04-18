from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from tinyagentos.agent_templates import (
    list_templates, get_template, CATEGORIES, EXTERNAL_SOURCES,
    fetch_external_index, fetch_external_template, template_stats,
    TEMPLATES,
)

router = APIRouter()

_VALID_SOURCES = {"builtin", "awesome-openclaw", "prompt-library", "user"}


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


@router.get("/api/personas/library")
async def api_personas_library(
    request: Request,
    source: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Aggregated persona library: builtin templates + user-authored personas.

    External sources (awesome-openclaw, prompt-library) are not yet wired —
    they require network fetches and are tracked as a follow-up.
    source filter returns 400 for unrecognised values.
    """
    if source is not None and source not in _VALID_SOURCES:
        return JSONResponse(
            {"error": f"unknown source '{source}'; valid: {sorted(_VALID_SOURCES)}"},
            status_code=400,
        )

    personas: list[dict] = []

    want_builtin = source in (None, "builtin")
    want_user = source in (None, "user")
    # External sources not implemented — return empty for now.

    if want_builtin:
        for tpl in TEMPLATES:
            sp = tpl.get("system_prompt", "") or ""
            personas.append({
                "source": "builtin",
                "id": tpl["id"],
                "name": tpl["name"],
                "description": tpl.get("description"),
                "preview": sp[:120],
            })

    if want_user:
        user_persona_store = getattr(request.app.state, "user_personas", None)
        if user_persona_store is not None:
            for row in user_persona_store.list():
                soul = row.get("soul_md", "") or ""
                personas.append({
                    "source": "user",
                    "id": row["id"],
                    "name": row["name"],
                    "description": row.get("description"),
                    "preview": soul[:120],
                })

    if q:
        q_lower = q.lower()
        personas = [
            p for p in personas
            if q_lower in (p["name"] or "").lower()
            or q_lower in (p["description"] or "").lower()
            or q_lower in (p["preview"] or "").lower()
        ]

    total = len(personas)
    page = personas[offset:offset + limit]
    return {"personas": page, "total": total}


@router.get("/api/templates/{template_id}")
async def api_get_template(template_id: str):
    """Get a single template by ID."""
    tmpl = get_template(template_id)
    if not tmpl:
        return JSONResponse({"error": "Template not found"}, status_code=404)
    return tmpl
