"""Desktop service icon API.

GET /api/apps/installed — list installed services that have a recorded
runtime location (host + port). These are the apps that get desktop icons
and can be opened in a taOS web-app window via the service proxy.

Only includes apps with a runtime_host/runtime_port entry, i.e. those
successfully installed via the LXC installer path. Docker-only apps
without proxy routing are excluded until their install path also records
a runtime location.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()

_GENERIC_ICON = "/static/app-icons/generic-service.svg"


def _resolve_icon(manifest_icon: str, manifest_dir) -> str:
    """Resolve the manifest's icon field to a URL string.

    Accepts:
    - Absolute URL paths like /static/app-icons/gitea.svg  → returned as-is.
    - http/https URLs                                        → returned as-is.
    - Relative paths (e.g. icons/gitea.svg) relative to
      the manifest dir — not currently served, so fall back
      to the generic icon.
    Returns the generic icon if the field is empty.
    """
    if not manifest_icon:
        return _GENERIC_ICON
    if manifest_icon.startswith("/") or manifest_icon.startswith("http"):
        return manifest_icon
    # Relative path — would need extra static-mount work; use generic for now.
    return _GENERIC_ICON


@router.get("/api/apps/installed")
async def list_installed_apps(request: Request):
    """Return installed services that have a live proxy location.

    Shape per item::

        {
            "app_id": "gitea-lxc",
            "display_name": "Gitea",
            "icon": "/static/app-icons/gitea.svg",
            "url": "/apps/gitea-lxc/",
            "category": "dev-tool",
            "backend": "lxc",
            "status": "running" | "unknown"
        }

    ``status`` is "running" when runtime_host + runtime_port are recorded;
    no live health check is performed here (that would add latency to every
    desktop load).
    """
    installed_apps: object = getattr(request.app.state, "installed_apps", None)
    registry: object = getattr(request.app.state, "registry", None)

    if installed_apps is None:
        return []

    rows = await installed_apps.list_installed()
    result = []

    for row in rows:
        app_id: str = row["app_id"]
        loc = await installed_apps.get_runtime_location(app_id)
        if loc is None:
            # No runtime location → not accessible via proxy → skip.
            continue

        # Best-effort manifest lookup for display metadata.
        manifest = registry.get(app_id) if registry is not None else None
        if manifest is not None:
            install_block = manifest.install or {}
            display_name: str = (
                install_block.get("display_name")
                or manifest.name
                or app_id
            )
            icon: str = _resolve_icon(
                install_block.get("icon") or manifest.icon or "",
                manifest.manifest_dir,
            )
            category: str = manifest.category or ""
        else:
            display_name = app_id
            icon = _GENERIC_ICON
            category = ""

        backend: str = loc.get("backend") or ""
        ui_path: str = loc.get("ui_path") or "/"
        url = f"/apps/{app_id}{ui_path}"

        result.append({
            "app_id": app_id,
            "display_name": display_name,
            "icon": icon,
            "url": url,
            "category": category,
            "backend": backend,
            "status": "running",
        })

    return result
