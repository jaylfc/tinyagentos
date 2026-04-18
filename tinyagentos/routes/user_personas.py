from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()


def _store(request: Request):
    return request.app.state.user_personas


class CreatePersonaBody(BaseModel):
    name: str
    soul_md: Optional[str] = ""
    agent_md: Optional[str] = ""
    description: Optional[str] = None


class UpdatePersonaBody(BaseModel):
    name: Optional[str] = None
    soul_md: Optional[str] = None
    agent_md: Optional[str] = None
    description: Optional[str] = None


@router.get("/api/user-personas")
async def list_personas(request: Request):
    personas = _store(request).list()
    return JSONResponse({"personas": personas})


@router.post("/api/user-personas")
async def create_persona(request: Request, body: CreatePersonaBody):
    pid = _store(request).create(
        name=body.name,
        soul_md=body.soul_md or "",
        agent_md=body.agent_md or "",
        description=body.description,
    )
    return JSONResponse({"id": pid}, status_code=201)


@router.get("/api/user-personas/{pid}")
async def get_persona(request: Request, pid: str):
    persona = _store(request).get(pid)
    if persona is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(persona)


@router.patch("/api/user-personas/{pid}")
async def update_persona(request: Request, pid: str, body: UpdatePersonaBody):
    if _store(request).get(pid) is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    _store(request).update(pid, **fields)
    return JSONResponse({"ok": True})


@router.delete("/api/user-personas/{pid}")
async def delete_persona(request: Request, pid: str):
    _store(request).delete(pid)
    return JSONResponse({"ok": True})
