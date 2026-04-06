from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from tinyagentos.agent_templates import list_templates, get_template, CATEGORIES

router = APIRouter()


@router.get("/templates", response_class=HTMLResponse)
async def templates_page(request: Request):
    templates_engine = request.app.state.templates
    return templates_engine.TemplateResponse(request, "templates.html", {
        "active_page": "templates",
    })


@router.get("/api/templates")
async def api_list_templates(category: str | None = None):
    """List agent templates, optionally filtered by category."""
    return {"templates": list_templates(category), "categories": CATEGORIES}


@router.get("/api/templates/{template_id}")
async def api_get_template(template_id: str):
    """Get a single template by ID."""
    tmpl = get_template(template_id)
    if not tmpl:
        return JSONResponse({"error": "Template not found"}, status_code=404)
    return tmpl
