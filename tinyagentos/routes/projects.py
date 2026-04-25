from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from tinyagentos.projects.folders import ensure_project_layout, write_project_yaml

router = APIRouter()


class CreateProjectIn(BaseModel):
    name: str
    slug: str
    description: str = ""
    settings: dict = Field(default_factory=dict)


class UpdateProjectIn(BaseModel):
    name: str | None = None
    description: str | None = None
    settings: dict | None = None


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if user and isinstance(user, dict) and "id" in user:
        return user["id"]
    return "system"


def _mirror(request: Request, project: dict) -> None:
    root = request.app.state.projects_root
    ensure_project_layout(root, project["slug"], project["name"])
    write_project_yaml(root, project["slug"], project)


@router.post("/api/projects")
async def create_project(payload: CreateProjectIn, request: Request):
    store = request.app.state.project_store
    try:
        p = await store.create_project(
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            settings=payload.settings,
            created_by=_user_id(request),
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=409)
    await store.log_activity(p["id"], _user_id(request), "project.created", {"slug": p["slug"]})
    _mirror(request, p)
    return p


@router.get("/api/projects")
async def list_projects(request: Request, status: str | None = "active"):
    store = request.app.state.project_store
    items = await store.list_projects(status=status)
    return {"items": items}


@router.get("/api/projects/{project_id}")
async def get_project(project_id: str, request: Request):
    store = request.app.state.project_store
    p = await store.get_project(project_id)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return p


@router.patch("/api/projects/{project_id}")
async def update_project(project_id: str, payload: UpdateProjectIn, request: Request):
    store = request.app.state.project_store
    await store.update_project(
        project_id,
        name=payload.name,
        description=payload.description,
        settings=payload.settings,
    )
    p = await store.get_project(project_id)
    if p is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    await store.log_activity(project_id, _user_id(request), "project.updated", payload.model_dump(exclude_none=True))
    _mirror(request, p)
    return p


@router.post("/api/projects/{project_id}/archive")
async def archive_project(project_id: str, request: Request):
    store = request.app.state.project_store
    await store.set_status(project_id, "archived")
    p = await store.get_project(project_id)
    await store.log_activity(project_id, _user_id(request), "project.archived", {})
    return p


@router.delete("/api/projects/{project_id}")
async def delete_project(project_id: str, request: Request):
    store = request.app.state.project_store
    await store.set_status(project_id, "deleted")
    p = await store.get_project(project_id)
    await store.log_activity(project_id, _user_id(request), "project.deleted", {})
    return p


class AddMemberIn(BaseModel):
    mode: str  # "native" | "clone"
    agent_id: str | None = None
    source_agent_id: str | None = None
    clone_memory: bool = True
    role: str = "member"


@router.post("/api/projects/{project_id}/members")
async def add_member(project_id: str, payload: AddMemberIn, request: Request):
    store = request.app.state.project_store
    project = await store.get_project(project_id)
    if project is None:
        return JSONResponse({"error": "project not found"}, status_code=404)

    if payload.mode == "native":
        if not payload.agent_id:
            return JSONResponse({"error": "agent_id required"}, status_code=400)
        member_id = payload.agent_id
        member_kind = "native"
        source_agent_id = None
        memory_seed = "none"
    elif payload.mode == "clone":
        if not payload.source_agent_id:
            return JSONResponse({"error": "source_agent_id required"}, status_code=400)
        member_id = f"{payload.source_agent_id}-{project['slug']}"
        member_kind = "clone"
        source_agent_id = payload.source_agent_id
        memory_seed = "snapshot" if payload.clone_memory else "empty"
    else:
        return JSONResponse({"error": "mode must be native|clone"}, status_code=400)

    await store.add_member(
        project_id=project_id,
        member_id=member_id,
        member_kind=member_kind,
        role=payload.role,
        source_agent_id=source_agent_id,
        memory_seed=memory_seed,
    )
    await store.log_activity(
        project_id, _user_id(request), "member.added",
        {"member_id": member_id, "kind": member_kind, "memory_seed": memory_seed},
    )
    members = await store.list_members(project_id)
    _mirror(request, {**project, "members": members})
    return next(m for m in members if m["member_id"] == member_id)


@router.get("/api/projects/{project_id}/members")
async def list_members(project_id: str, request: Request):
    store = request.app.state.project_store
    return {"items": await store.list_members(project_id)}


@router.delete("/api/projects/{project_id}/members/{member_id}")
async def remove_member(project_id: str, member_id: str, request: Request):
    store = request.app.state.project_store
    await store.remove_member(project_id, member_id)
    await store.log_activity(project_id, _user_id(request), "member.removed", {"member_id": member_id})
    project = await store.get_project(project_id)
    members = await store.list_members(project_id)
    if project is not None:
        _mirror(request, {**project, "members": members})
    return {"ok": True}
