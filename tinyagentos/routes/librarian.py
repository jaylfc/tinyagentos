from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import taosmd.agents as tm_agents
from taosmd.agents import AgentNotFoundError

router = APIRouter()


class LibrarianPatch(BaseModel):
    enabled: bool | None = None
    model: str | None = None
    clear_model: bool = False
    tasks: dict[str, bool] | None = None
    fanout: str | None = None
    fanout_auto_scale: bool | None = None


@router.get("/api/agents/{slug}/librarian")
async def get_librarian(slug: str):
    try:
        return tm_agents.get_librarian(slug)
    except AgentNotFoundError:
        return JSONResponse(status_code=404, content={"detail": f"agent {slug!r} not found"})


@router.patch("/api/agents/{slug}/librarian")
async def patch_librarian(slug: str, body: LibrarianPatch):
    kwargs = body.model_dump(exclude_none=True)
    # clear_model=False is the default and should not be forwarded unless explicitly True
    if not body.clear_model:
        kwargs.pop("clear_model", None)
    try:
        result = tm_agents.set_librarian(slug, **kwargs)
        return result
    except AgentNotFoundError:
        return JSONResponse(status_code=404, content={"detail": f"agent {slug!r} not found"})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
