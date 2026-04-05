from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from tinyagentos.backend_adapters import check_backend_health
from tinyagentos.qmd_db import QmdDatabase

router = APIRouter()

QMD_CACHE_DIR = Path.home() / ".cache" / "qmd"


def _get_agent_db(agent: dict) -> QmdDatabase | None:
    index_name = agent.get("qmd_index", "index")
    db_path = QMD_CACHE_DIR / f"{index_name}.sqlite"
    try:
        return QmdDatabase(db_path)
    except FileNotFoundError:
        return None


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse("dashboard.html", {"request": request, "active_page": "dashboard"})


@router.get("/api/health")
async def api_health(request: Request):
    config = request.app.state.config
    return {
        "status": "ok",
        "agents": len(config.agents),
        "backends": len(config.backends),
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

    agents_total = len(config.agents)
    agents_online = 0
    total_vectors = 0
    for agent in config.agents:
        db = _get_agent_db(agent)
        if db:
            total_vectors += db.vector_count()
            agents_online += 1

    http_client = request.app.state.http_client
    response_times = []
    for backend in config.backends:
        result = await check_backend_health(http_client, backend)
        if result["status"] == "ok":
            response_times.append(result["response_ms"])
    avg_response_ms = int(sum(response_times) / len(response_times)) if response_times else None

    qmd_health = await request.app.state.qmd_client.health()
    qmd_latency_ms = qmd_health.get("response_ms") if qmd_health.get("status") != "error" else None

    return templates.TemplateResponse("partials/kpi_cards.html", {
        "request": request,
        "agents_online": agents_online,
        "agents_total": agents_total,
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
    return templates.TemplateResponse("partials/backend_status.html", {"request": request, "backends": backends})


@router.get("/api/partials/agent-summary", response_class=HTMLResponse)
async def agent_summary(request: Request):
    config = request.app.state.config
    templates = request.app.state.templates
    agents = []
    for agent in config.agents:
        db = _get_agent_db(agent)
        agents.append({
            "name": agent["name"],
            "color": agent.get("color", "#888"),
            "status": "ok" if db else "error",
            "vectors": db.vector_count() if db else 0,
            "last_embedded": db.last_embedded_at() if db else None,
        })
    return templates.TemplateResponse("partials/agent_summary.html", {"request": request, "agents": agents})


@router.get("/api/metrics/{name}")
async def api_metrics(request: Request, name: str, range: str = "24h"):
    metrics = request.app.state.metrics
    import time
    now = int(time.time())
    range_map = {"1h": 3600, "24h": 86400, "7d": 604800, "30d": 2592000}
    seconds = range_map.get(range, 86400)
    results = await metrics.query(name, start=now - seconds, end=now)
    return results
