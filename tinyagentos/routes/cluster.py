from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from tinyagentos.cluster.capabilities import potential_capabilities as _potential_capabilities
from tinyagentos.cluster.optimiser import ClusterOptimiser
from tinyagentos.cluster.worker_protocol import WorkerInfo

router = APIRouter()


class WorkerRegister(BaseModel):
    name: str
    url: str
    hardware: dict = {}
    backends: list[dict] = []
    models: list[str] = []
    capabilities: list[str] = []
    platform: str = ""
    # KV quant support advertised at registration time.  Defaults to ["fp16"]
    # so legacy workers that don't send this field still get a sensible value.
    kv_cache_quant_support: list[str] = ["fp16"]


class HeartbeatBody(BaseModel):
    name: str
    load: float = 0.0
    models: list[str] | None = None
    # Backend-driven fields (worker agent v2+). Both optional so legacy
    # worker agents that only report load + models still validate.
    backends: list[dict] | None = None
    capabilities: list[str] | None = None
    # KV quant support, forwarded from the worker's detect_kv_quant_support()
    # result.  None means the heartbeat came from an old worker agent that
    # doesn't know about this field; the controller leaves the existing value
    # unchanged rather than overwriting with a default.
    kv_cache_quant_support: list[str] | None = None


class RouteRequest(BaseModel):
    capability: str
    method: str = "POST"
    path: str
    body: dict | None = None
    timeout: float = 60


class MoveRequest(BaseModel):
    item: str
    from_worker: str | None = None
    to_worker: str


@router.get("/cluster", response_class=HTMLResponse)
async def cluster_page(request: Request):
    templates = request.app.state.templates
    cluster = request.app.state.cluster_manager
    workers = cluster.get_workers()
    # Collect all capabilities across workers
    all_caps = sorted({cap for w in workers for cap in w.capabilities if w.status == "online"})
    return templates.TemplateResponse(request, "cluster.html", {
        "active_page": "cluster",
        "workers": workers,
        "capabilities": all_caps,
    })


@router.get("/api/cluster/workers")
async def list_workers(request: Request):
    cluster = request.app.state.cluster_manager
    registry = getattr(request.app.state, "registry", None)
    workers = cluster.get_workers()
    result = []
    for w in workers:
        d = asdict(w)
        if registry is not None:
            tier_id, pot_caps = _potential_capabilities(w.hardware, registry)
            d["tier_id"] = tier_id
            d["potential_capabilities"] = pot_caps
            # Keep WorkerInfo fields in sync too so in-memory state is consistent
            w.tier_id = tier_id
            w.potential_capabilities = pot_caps
        result.append(d)
    return result


@router.post("/api/cluster/workers")
async def register_worker(request: Request, body: WorkerRegister):
    cluster = request.app.state.cluster_manager
    if not body.name or not body.url:
        return JSONResponse({"error": "name and url are required"}, status_code=400)
    info = WorkerInfo(
        name=body.name,
        url=body.url,
        hardware=body.hardware,
        backends=body.backends,
        models=body.models,
        capabilities=body.capabilities,
        platform=body.platform,
        kv_cache_quant_support=body.kv_cache_quant_support,
    )
    await cluster.register_worker(info)
    return {"status": "registered", "name": body.name}


@router.post("/api/cluster/heartbeat")
async def worker_heartbeat(request: Request, body: HeartbeatBody):
    cluster = request.app.state.cluster_manager
    ok = cluster.heartbeat(
        body.name,
        load=body.load,
        models=body.models,
        backends=body.backends,
        capabilities=body.capabilities,
        kv_cache_quant_support=body.kv_cache_quant_support,
    )
    if not ok:
        return JSONResponse({"error": "Worker not registered"}, status_code=404)
    return {"status": "ok"}


@router.delete("/api/cluster/workers/{name}")
async def unregister_worker(request: Request, name: str):
    cluster = request.app.state.cluster_manager
    removed = cluster.unregister_worker(name)
    if not removed:
        return JSONResponse({"error": "Worker not found"}, status_code=404)
    return {"status": "removed", "name": name}


@router.get("/api/cluster/capabilities")
async def list_capabilities(request: Request):
    cluster = request.app.state.cluster_manager
    workers = cluster.get_workers()
    caps: dict[str, list[str]] = {}
    for w in workers:
        if w.status != "online":
            continue
        for cap in w.capabilities:
            caps.setdefault(cap, []).append(w.name)
    return caps


@router.get("/api/cluster/kv-quant-options")
async def kv_quant_options(request: Request):
    """Return the set-union of KV cache quant types across all online workers.

    The deploy wizard fetches this to decide whether to show a KV quant
    dropdown.  When only ["fp16"] is returned, the wizard shows nothing — no
    dead toggle, no greyed-out control.  As soon as any online worker
    advertises a second type the dropdown materialises automatically.

    Response shape: {"options": ["fp16", "turboquant-k3v2", ...]}
    """
    cluster = request.app.state.cluster_manager
    options = cluster.kv_quant_union()
    return {"options": options}


@router.get("/api/cluster/backends")
async def cluster_backends(request: Request):
    """Aggregate backend catalog across every online worker in the mesh.

    Unions each worker's latest-heartbeat BackendCatalog into a single
    cluster-wide view. This is the cluster sibling of /api/scheduler/backends
    (which shows only the local controller's backends). Used by:

    - Cluster page UI to show 'what the whole mesh can do right now'
    - Scheduler Phase 2 cluster-aware dispatch to pick remote resources
    - Model Browser's 'available on cluster' filter
    """
    cluster = request.app.state.cluster_manager
    return cluster.aggregate_catalog()


@router.post("/api/cluster/route")
async def route_task(request: Request, body: RouteRequest):
    task_router = request.app.state.task_router
    data, worker_name = await task_router.route_request(
        capability=body.capability,
        method=body.method,
        path=body.path,
        body=body.body,
        timeout=body.timeout,
    )
    if data is None:
        return JSONResponse(
            {"error": f"No available worker for capability '{body.capability}'"},
            status_code=503,
        )
    return {"data": data, "worker": worker_name}


@router.get("/api/cluster/optimise")
async def optimise_cluster(request: Request):
    cluster = request.app.state.cluster_manager
    optimiser = ClusterOptimiser(cluster)
    return optimiser.analyse()


@router.post("/api/cluster/move")
async def move_model(request: Request, body: MoveRequest):
    cluster = request.app.state.cluster_manager
    to_worker = cluster.get_worker(body.to_worker)
    if not to_worker:
        return JSONResponse({"error": f"Worker '{body.to_worker}' not found"}, status_code=404)
    if to_worker.status != "online":
        return JSONResponse({"error": f"Worker '{body.to_worker}' is not online"}, status_code=400)

    # If from_worker specified, remove the item from it
    if body.from_worker:
        from_w = cluster.get_worker(body.from_worker)
        if from_w and body.item in from_w.models:
            from_w.models.remove(body.item)
        if from_w and body.item in from_w.capabilities:
            from_w.capabilities.remove(body.item)

    # Add to target worker's models if not already there
    if body.item not in to_worker.models:
        to_worker.models.append(body.item)

    return {"status": "moved", "item": body.item, "to": body.to_worker}
