"""HTTP routes for incus cross-host container migration and remote management."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tinyagentos.containers import migrate_container, remote_add, remote_generate_token, remote_list, remote_remove
from tinyagentos.cluster.service_migrator import migrate_service

router = APIRouter()


class RemoteAddBody(BaseModel):
    name: str
    url: str
    token: str


class GenerateTokenBody(BaseModel):
    client_name: str
    projects: list[str] | None = None
    restricted: bool = False


class MigrateBody(BaseModel):
    container: str
    target_remote: str
    new_name: str | None = None
    keep_source: bool = False
    stateless: bool = True
    timeout: int = 600


class MigrateServiceBody(BaseModel):
    app_id: str
    target_remote: str
    keep_source: bool = False
    source_remote: str | None = None


@router.post("/api/cluster/remotes")
async def add_remote(body: RemoteAddBody):
    """Register an incus remote host using a one-time token."""
    if not body.name or not body.url:
        return JSONResponse({"error": "name and url are required"}, status_code=400)
    if not body.token:
        return JSONResponse({"error": "token is required"}, status_code=400)
    result = await remote_add(body.name, body.url, token=body.token)
    if not result["success"]:
        return JSONResponse({"error": result["output"]}, status_code=500)
    return {"status": "registered", "name": body.name}


@router.post("/api/cluster/remotes/token")
async def generate_token(body: GenerateTokenBody):
    """Generate a one-time enrollment token on this host for a remote client."""
    if not body.client_name:
        return JSONResponse({"error": "client_name is required"}, status_code=400)
    result = await remote_generate_token(
        body.client_name,
        projects=body.projects,
        restricted=body.restricted,
    )
    if not result["success"]:
        return JSONResponse({"error": result["output"]}, status_code=500)
    return {"token": result["token"]}


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


@router.post("/api/cluster/migrate-service")
async def migrate_service_route(request: Request, body: MigrateServiceBody):
    """Arch-portable service migration: deploy fresh on target, restore state paths."""
    if not body.app_id or not body.target_remote:
        return JSONResponse(
            {"error": "app_id and target_remote are required"}, status_code=400
        )

    registry = request.app.state.registry
    manifest = registry.get(body.app_id)
    if not manifest:
        return JSONResponse(
            {"error": f"App '{body.app_id}' not found in catalog"}, status_code=404
        )

    state_paths: list[str] = manifest.install.get("state_paths", [])
    if not state_paths:
        # Fall back to top-level manifest field for manifests that declare it there.
        import yaml as _yaml
        if manifest.manifest_dir is not None:
            lxc_manifest_path = manifest.manifest_dir / "manifest-lxc.yaml"
            if lxc_manifest_path.exists():
                _data = _yaml.safe_load(lxc_manifest_path.read_text())
                state_paths = _data.get("state_paths", [])

    if not state_paths:
        return JSONResponse(
            {"error": f"App '{body.app_id}' has no state_paths defined in its manifest"},
            status_code=400,
        )

    service_name: str = manifest.install.get("service_name", "")
    if not service_name and manifest.manifest_dir is not None:
        import yaml as _yaml
        lxc_manifest_path = manifest.manifest_dir / "manifest-lxc.yaml"
        if lxc_manifest_path.exists():
            _data = _yaml.safe_load(lxc_manifest_path.read_text())
            service_name = _data.get("service_name", body.app_id)

    if not service_name:
        service_name = body.app_id

    try:
        result = await migrate_service(
            body.app_id,
            body.target_remote,
            install_config=manifest.install,
            state_paths=state_paths,
            service_name=service_name,
            keep_source=body.keep_source,
            source_remote=body.source_remote,
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

    if not result["success"]:
        return JSONResponse({"error": result["error"]}, status_code=500)
    return result
