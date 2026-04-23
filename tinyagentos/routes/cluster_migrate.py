"""HTTP routes for incus cross-host container migration and remote management."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tinyagentos.containers import migrate_container, remote_add, remote_list, remote_remove

router = APIRouter()


class RemoteAddBody(BaseModel):
    name: str
    url: str
    trust_password: str | None = None
    tls_cert_fingerprint: str | None = None


class MigrateBody(BaseModel):
    container: str
    target_remote: str
    new_name: str | None = None
    keep_source: bool = False
    stateless: bool = True
    timeout: int = 600


@router.post("/api/cluster/remotes")
async def add_remote(body: RemoteAddBody):
    """Register an incus remote host."""
    if not body.name or not body.url:
        return JSONResponse({"error": "name and url are required"}, status_code=400)
    result = await remote_add(
        body.name,
        body.url,
        tls_cert_fingerprint=body.tls_cert_fingerprint,
        trust_password=body.trust_password,
    )
    if not result["success"]:
        return JSONResponse({"error": result["output"]}, status_code=500)
    return {"status": "registered", "name": body.name}


@router.get("/api/cluster/remotes")
async def list_remotes():
    """List registered incus remotes."""
    return await remote_list()


@router.delete("/api/cluster/remotes/{name}")
async def remove_remote(name: str):
    """Remove a registered incus remote."""
    result = await remote_remove(name)
    if not result["success"]:
        return JSONResponse({"error": result["output"]}, status_code=500)
    return {"status": "removed", "name": name}


@router.post("/api/cluster/migrate")
async def migrate(body: MigrateBody):
    """Move or copy a container to a remote incus host."""
    if not body.container or not body.target_remote:
        return JSONResponse(
            {"error": "container and target_remote are required"}, status_code=400
        )
    result = await migrate_container(
        body.container,
        body.target_remote,
        new_name=body.new_name,
        keep_source=body.keep_source,
        stateless=body.stateless,
        timeout=body.timeout,
    )
    if not result["success"]:
        return JSONResponse({"error": result["error"]}, status_code=500)
    return result
