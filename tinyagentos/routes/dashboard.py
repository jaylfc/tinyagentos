from __future__ import annotations

import time
from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from tinyagentos.agent_db import get_agent_summaries
from tinyagentos.backend_adapters import check_backend_health
from tinyagentos.first_boot import is_first_boot, mark_setup_complete

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    data_dir = request.app.state.config_path.parent
    if is_first_boot(data_dir):
        return RedirectResponse(url="/setup", status_code=303)
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "dashboard.html", {"active_page": "dashboard"})


@router.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    templates = request.app.state.templates
    hardware = request.app.state.hardware_profile
    hw_data = asdict(hardware)
    hw_data["profile_id"] = hardware.profile_id
    return templates.TemplateResponse(request, "setup.html", {
        "active_page": "setup",
        "hardware": hardware,
    })


@router.post("/setup/complete")
async def setup_complete(request: Request):
    data_dir = request.app.state.config_path.parent
    form = await request.form()
    password = form.get("password", "")
    if password:
        auth_mgr = request.app.state.auth
        if not auth_mgr.is_configured():
            auth_mgr.set_password(password)
    mark_setup_complete(data_dir)
    response = RedirectResponse(url="/", status_code=303)
    # If password was just set, create a session so user is logged in
    if password:
        token = auth_mgr.create_session()
        response.set_cookie("taos_session", token, httponly=True, samesite="lax", max_age=auth_mgr.session_ttl)
    return response


@router.get("/api/capabilities")
async def api_capabilities(request: Request):
    """Return all capabilities with their available/locked status and unlock hints."""
    cap_checker = request.app.state.capabilities
    return {"capabilities": cap_checker.get_all_capabilities()}


@router.get("/api/health")
async def api_health(request: Request):
    """System health check -- returns agent and backend counts."""
    config = request.app.state.config
    return {
        "status": "ok",
        "agents": len(config.agents),
        "backends": len(config.backends),
    }


@router.get("/api/system")
async def api_system(request: Request):
    """Comprehensive system overview -- hardware, resources, platform stats."""
    import psutil
    from dataclasses import asdict

    config = request.app.state.config
    hw = request.app.state.hardware_profile
    registry = request.app.state.registry

    hw_data = asdict(hw)
    hw_data["profile_id"] = hw.profile_id

    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return {
        "hardware": hw_data,
        "resources": {
            "cpu_percent": psutil.cpu_percent(),
            "ram_total_mb": mem.total // (1024 * 1024),
            "ram_used_mb": mem.used // (1024 * 1024),
            "ram_percent": mem.percent,
            "disk_total_gb": disk.total // (1024 ** 3),
            "disk_used_gb": disk.used // (1024 ** 3),
            "disk_percent": disk.percent,
        },
        "platform": {
            "version": "0.1.0",
            "agents": len(config.agents),
            "backends": len(config.backends),
            "catalog_apps": len(registry.list_available()),
            "installed_apps": len(registry.list_installed()),
        },
        "cluster": _get_cluster_stats(request),
    }


def _get_cluster_stats(request) -> dict:
    """Aggregate cluster statistics."""
    cluster = getattr(request.app.state, "cluster", None)
    if not cluster:
        return {"workers": 0, "online": 0, "total_vram_mb": 0, "total_ram_mb": 0, "capabilities": []}
    workers = cluster.get_workers()
    online = [w for w in workers if w.status == "online"]
    total_vram = 0
    total_ram = 0
    all_caps = set()
    for w in online:
        hw = w.hardware if isinstance(w.hardware, dict) else {}
        total_ram += hw.get("ram_mb", 0)
        gpu = hw.get("gpu", {})
        if isinstance(gpu, dict):
            total_vram += gpu.get("vram_mb", 0)
        all_caps.update(w.capabilities)
    return {
        "workers": len(workers),
        "online": len(online),
        "total_vram_mb": total_vram,
        "total_ram_mb": total_ram,
        "capabilities": sorted(all_caps),
    }


@router.get("/api/backends")
async def api_backends(request: Request):
    """List all configured backends with live health status and fallback info."""
    config = request.app.state.config
    http_client = request.app.state.http_client
    fallback = request.app.state.fallback
    results = []
    for backend in config.backends:
        result = await check_backend_health(http_client, backend)
        results.append(result)
    primary = fallback.get_primary_backend()
    return {
        "backends": results,
        "primary": primary["name"] if primary else None,
        "fallback_status": fallback.get_status(),
    }


@router.get("/api/partials/kpi-cards", response_class=HTMLResponse)
async def kpi_cards(request: Request):
    """HTMX partial: KPI cards with agent, vector, and latency stats."""
    config = request.app.state.config
    templates = request.app.state.templates

    summaries = get_agent_summaries(config)
    agents_online = sum(1 for s in summaries if s["status"] == "ok")
    total_vectors = sum(s["vectors"] for s in summaries)

    http_client = request.app.state.http_client
    response_times = []
    for backend in config.backends:
        result = await check_backend_health(http_client, backend)
        if result["status"] == "ok":
            response_times.append(result["response_ms"])
    avg_response_ms = int(sum(response_times) / len(response_times)) if response_times else None

    qmd_health = await request.app.state.qmd_client.health()
    qmd_latency_ms = qmd_health.get("response_ms") if qmd_health.get("status") != "error" else None

    return templates.TemplateResponse(request, "partials/kpi_cards.html", {
        "agents_online": agents_online,
        "agents_total": len(summaries),
        "total_vectors": total_vectors,
        "avg_response_ms": avg_response_ms,
        "qmd_latency_ms": qmd_latency_ms,
    })


@router.get("/api/partials/backend-status", response_class=HTMLResponse)
async def backend_status(request: Request):
    """HTMX partial: backend status table sorted by priority."""
    config = request.app.state.config
    http_client = request.app.state.http_client
    templates = request.app.state.templates
    backends = []
    for backend in config.backends:
        result = await check_backend_health(http_client, backend)
        backends.append(result)
    backends.sort(key=lambda b: b.get("priority", 99))
    return templates.TemplateResponse(request, "partials/backend_status.html", {"backends": backends})


@router.get("/api/partials/agent-summary", response_class=HTMLResponse)
async def agent_summary(request: Request):
    """HTMX partial: agent summary list."""
    config = request.app.state.config
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "partials/agent_summary.html", {
        "agents": get_agent_summaries(config),
    })


@router.get("/api/metrics/{name}")
async def api_metrics(request: Request, name: str, range: str = "24h"):
    """Query time-series metrics by name and time range."""
    metrics = request.app.state.metrics
    now = int(time.time())
    range_map = {"1h": 3600, "24h": 86400, "7d": 604800, "30d": 2592000}
    seconds = range_map.get(range, 86400)
    results = await metrics.query(name, start=now - seconds, end=now)
    return results
