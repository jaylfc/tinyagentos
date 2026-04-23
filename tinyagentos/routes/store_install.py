from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from tinyagentos.installers.lxc_installer import LXCInstaller

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_current_user(request: Request) -> dict | None:
    """Return the currently authenticated user or None."""
    auth = getattr(request.app.state, "auth", None)
    if auth is None:
        return None
    token = request.cookies.get("taos_session", "")
    return auth.session_user(token)


@router.post("/api/store/install-v2")
async def install_app(request: Request):
    body = await request.json()
    app_id = body.get("app_id", "")
    if not app_id:
        return JSONResponse({"error": "app_id required"}, status_code=400)

    # Resolve manifest to determine backend.
    registry = getattr(request.app.state, "registry", None)
    manifest = None
    install_config = {}
    backend = "docker"  # default

    if registry is not None:
        manifest = registry.get(app_id)

    if manifest is not None:
        install_block = getattr(manifest, "install", None) or {}
        if isinstance(install_block, dict):
            install_config = install_block
            backend = install_config.get("backend", install_config.get("method", "docker"))
        # manifest.install might be an object with a .get method or attributes
        elif hasattr(install_block, "get"):
            backend = install_block.get("method", "docker")

    # Override with body-supplied metadata if provided.
    meta = body.get("metadata") or {}
    if isinstance(meta, dict) and meta.get("backend"):
        backend = meta["backend"]
    if isinstance(meta, dict) and meta.get("method"):
        backend = meta["method"]

    if backend == "lxc":
        # LXC installs require admin_password.
        admin_password = body.get("admin_password", "")
        if not admin_password:
            return JSONResponse(
                {"error": "admin_password is required for LXC installs"},
                status_code=400,
            )

        user = _get_current_user(request)
        taos_username = (user or {}).get("username", "admin")
        taos_email = (user or {}).get("email", "")

        installer = LXCInstaller()
        try:
            result = await installer.install(
                app_id,
                install_config,
                admin_password=admin_password,
                taos_username=taos_username,
                taos_email=taos_email,
            )
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

        if not result.get("success"):
            return JSONResponse({"error": result.get("error", "install failed")}, status_code=500)

        # Persist in installed-apps store if available.
        store = getattr(request.app.state, "installed_apps", None)
        if store is not None:
            await store.install(app_id, body.get("version", ""), meta)

        return JSONResponse({"ok": True, "app_id": app_id, "status": "installed", **result})

    # Default: delegate to InstalledAppsStore (docker/pip/download).
    store = request.app.state.installed_apps
    await store.install(app_id, body.get("version", ""), meta)
    return JSONResponse({"ok": True, "app_id": app_id, "status": "installed"})


@router.post("/api/store/uninstall-v2")
async def uninstall_app(request: Request):
    body = await request.json()
    app_id = body.get("app_id", "")
    if not app_id:
        return JSONResponse({"error": "app_id required"}, status_code=400)

    # Determine backend from manifest or body metadata.
    registry = getattr(request.app.state, "registry", None)
    backend = "docker"
    if registry is not None:
        manifest = registry.get(app_id)
        if manifest is not None:
            install_block = getattr(manifest, "install", None) or {}
            if isinstance(install_block, dict):
                backend = install_block.get("backend", install_block.get("method", "docker"))
    meta = body.get("metadata") or {}
    if isinstance(meta, dict) and meta.get("backend"):
        backend = meta["backend"]
    if isinstance(meta, dict) and meta.get("method"):
        backend = meta["method"]

    container_error: str | None = None
    if backend == "lxc":
        try:
            installer = LXCInstaller()
            await installer.uninstall(app_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LXC container destroy failed for %s: %s", app_id, exc)
            container_error = str(exc)

    store = request.app.state.installed_apps
    removed = await store.uninstall(app_id)
    resp: dict = {"ok": removed, "app_id": app_id, "status": "uninstalled" if removed else "not_installed"}
    if container_error is not None:
        resp["container_error"] = container_error
    return JSONResponse(resp)


@router.get("/api/store/installed-v2")
async def list_installed(request: Request):
    store = request.app.state.installed_apps
    items = await store.list_installed()
    return JSONResponse({"installed": items})
