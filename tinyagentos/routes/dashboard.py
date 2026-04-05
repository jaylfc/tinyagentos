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
    mark_setup_complete(data_dir)
    return RedirectResponse(url="/", status_code=303)


@router.get("/api/health")
async def api_health(request: Request):
    config = request.app.state.config
    return {
        "status": "ok",
        "agents": len(config.agents),
        "backends": len(config.backends),
    }


@router.get("/api/system")
async def api_system(request: Request):
    """Comprehensive system overview in one call."""
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
    }


@router.get("/api/backends")
async def api_backends(request: Request):
    config = request.app.state.config
    http_client = request.app.state.http_client
    results = []
    for backend in config.backends:
        result = await check_backend_health(http_client, backend)
        results.append(result)
    return results


@router.get("/api/partials/kpi-cards", response_class=HTMLResponse)
async def kpi_cards(request: Request):
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
    config = request.app.state.config
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "partials/agent_summary.html", {
        "agents": get_agent_summaries(config),
    })


@router.get("/api/metrics/{name}")
async def api_metrics(request: Request, name: str, range: str = "24h"):
    metrics = request.app.state.metrics
    now = int(time.time())
    range_map = {"1h": 3600, "24h": 86400, "7d": 604800, "30d": 2592000}
    seconds = range_map.get(range, 86400)
    results = await metrics.query(name, start=now - seconds, end=now)
    return results
