from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

router = APIRouter()


class SecretCreate(BaseModel):
    name: str
    value: str
    category: str = "general"
    description: str = ""
    agents: list[str] = []


class SecretUpdate(BaseModel):
    value: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    agents: Optional[list[str]] = None


@router.get("/secrets", response_class=HTMLResponse)
async def secrets_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "secrets.html", {
        "active_page": "secrets",
    })


@router.get("/api/secrets/categories")
async def list_categories(request: Request):
    store = request.app.state.secrets
    categories = await store.get_categories()
    return categories


@router.get("/api/secrets/agent/{agent_name}")
async def get_agent_secrets(request: Request, agent_name: str):
    store = request.app.state.secrets
    secrets = await store.get_agent_secrets(agent_name)
    return secrets


@router.get("/api/secrets/{name}")
async def get_secret(request: Request, name: str):
    store = request.app.state.secrets
    secret = await store.get(name)
    if not secret:
        return JSONResponse({"error": "Secret not found"}, status_code=404)
    return secret


@router.get("/api/secrets")
async def list_secrets(request: Request, category: str | None = None):
    store = request.app.state.secrets
    secrets = await store.list(category=category)
    # Mask values in list view
    for s in secrets:
        s["value"] = "***"
    return secrets


@router.post("/api/secrets")
async def add_secret(request: Request, body: SecretCreate):
    store = request.app.state.secrets
    # Check for duplicate
    existing = await store.get(body.name)
    if existing:
        return JSONResponse({"error": "Secret already exists"}, status_code=409)
    secret_id = await store.add(
        name=body.name,
        value=body.value,
        category=body.category,
        description=body.description,
        agents=body.agents,
    )
    return {"id": secret_id, "status": "created"}


@router.put("/api/secrets/{name}")
async def update_secret(request: Request, name: str, body: SecretUpdate):
    store = request.app.state.secrets
    updated = await store.update(
        name=name,
        value=body.value,
        category=body.category,
        description=body.description,
        agents=body.agents,
    )
    if not updated:
        return JSONResponse({"error": "Secret not found"}, status_code=404)
    return {"status": "updated"}


@router.delete("/api/secrets/{name}")
async def delete_secret(request: Request, name: str):
    store = request.app.state.secrets
    deleted = await store.delete(name)
    if not deleted:
        return JSONResponse({"error": "Secret not found"}, status_code=404)
    return {"status": "deleted"}
