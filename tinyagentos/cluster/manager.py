from __future__ import annotations
import asyncio
import logging
import time
from tinyagentos.cluster.worker_protocol import WorkerInfo

logger = logging.getLogger(__name__)

HEARTBEAT_TIMEOUT = 30  # seconds before marking worker offline


def _format_hw(hw) -> str:
    """Format hardware info for notification messages."""
    if not isinstance(hw, dict):
        return "Unknown hardware"
    parts = []
    ram = hw.get("ram_mb", 0)
    if ram:
        parts.append(f"{ram // 1024}GB RAM")
    gpu = hw.get("gpu", {})
    if gpu.get("type") not in (None, "none", ""):
        vram = gpu.get("vram_mb", 0)
        parts.append(f"{gpu.get('model', gpu['type'])}" + (f" {vram // 1024}GB" if vram else ""))
    npu = hw.get("npu", {})
    if npu.get("type", "none") != "none":
        parts.append(f"{npu['type']} {npu.get('tops', 0)} TOPS")
    return ", ".join(parts) if parts else "CPU only"


class ClusterManager:
    def __init__(self, notifications=None, capabilities=None):
        self._workers: dict[str, WorkerInfo] = {}
        self._monitor_task: asyncio.Task | None = None
        self._notifications = notifications  # NotificationStore, optional
        self._capabilities = capabilities    # CapabilityChecker, optional

    async def start(self):
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self):
        if self._monitor_task:
            self._monitor_task.cancel()

    async def register_worker(self, info: WorkerInfo) -> None:
        # Snapshot capabilities before adding worker
        caps_before = set()
        if self._capabilities:
            caps_before = {k for k, v in self._capabilities.get_all_capabilities().items() if v["available"]}

        info.registered_at = time.time()
        info.last_heartbeat = time.time()
        info.status = "online"
        self._workers[info.name] = info
        logger.info(f"Worker registered: {info.name} ({info.platform}, {len(info.capabilities)} capabilities)")

        # Check what capabilities were unlocked by this worker
        if self._notifications:
            newly_unlocked = []
            if self._capabilities:
                caps_after = {k for k, v in self._capabilities.get_all_capabilities().items() if v["available"]}
                newly_unlocked = sorted(caps_after - caps_before)

            hw_summary = _format_hw(info.hardware)
            msg = f"Platform: {info.platform}, {hw_summary}"
            if newly_unlocked:
                msg += f"\n\nNewly unlocked: {', '.join(newly_unlocked)}"
                msg += "\n\nConsider running cluster optimisation to redistribute workloads."

            await self._notifications.emit_event(
                "worker.join",
                f"Worker '{info.name}' joined the cluster",
                msg,
                level="info",
            )

    def kv_quant_union(self) -> list[str]:
        """Return the set-union of KV cache quant types across all online workers.

        Always includes "fp16" as the baseline.  If every online worker only
        supports fp16 the result is ["fp16"].  The deploy wizard uses this to
        decide whether to show the KV quant dropdown at all — if the list has
        only one entry the control must not be rendered.
        """
        types: set[str] = {"fp16"}
        for w in self._workers.values():
            if w.status != "online":
                continue
            types.update(w.kv_cache_quant_support or ["fp16"])
        return sorted(types)

    def heartbeat(
        self,
        name: str,
        load: float = 0.0,
        models: list[str] | None = None,
        backends: list[dict] | None = None,
        capabilities: list[str] | None = None,
        kv_cache_quant_support: list[str] | None = None,
    ) -> bool:
        """Accept a worker heartbeat.

        Backend-driven: when ``backends`` or ``capabilities`` are supplied
        (worker agent v2+), overwrite the worker's cached view so the
        cluster-wide catalog stays fresh. Old-style heartbeats that only
        carry load/models still work.
        """
        worker = self._workers.get(name)
        if not worker:
            return False
        worker.last_heartbeat = time.time()
        worker.load = load
        worker.status = "online"
        if models is not None:
            worker.models = models
        if backends is not None:
            worker.backends = backends
            # Derive a flat model list from the live backend catalog for
            # compatibility with the existing worker.models field
            flat_models: list[str] = []
            for b in backends:
                for m in b.get("models") or []:
                    name_m = m.get("name") or m.get("id") or ""
                    if name_m and name_m not in flat_models:
                        flat_models.append(name_m)
            worker.models = flat_models
        if capabilities is not None:
            worker.capabilities = list(capabilities)
        if kv_cache_quant_support is not None:
            worker.kv_cache_quant_support = list(kv_cache_quant_support)
        return True

    def unregister_worker(self, name: str) -> bool:
        return self._workers.pop(name, None) is not None

    def get_workers(self) -> list[WorkerInfo]:
        return list(self._workers.values())

    def get_worker(self, name: str) -> WorkerInfo | None:
        return self._workers.get(name)

    def get_workers_for_capability(self, capability: str) -> list[WorkerInfo]:
        """Get online workers that support a capability, sorted by priority (lowest load first)."""
        eligible = [
            w for w in self._workers.values()
            if w.status == "online" and capability in w.capabilities
        ]
        return sorted(eligible, key=lambda w: w.load)

    def get_best_worker(self, capability: str) -> WorkerInfo | None:
        """Get the best available worker for a capability."""
        workers = self.get_workers_for_capability(capability)
        return workers[0] if workers else None

    def aggregate_catalog(self) -> dict:
        """Cluster-wide union of every online worker's live BackendCatalog.

        Each online worker reports its own backends + models on every
        heartbeat. This method joins them into a single view keyed on
        ``f"{worker_name}:{backend_name}"`` so the Cluster page and the
        cluster-aware scheduler dispatch (Phase 2) can see 'what the
        entire mesh can do right now' without polling every worker
        individually.

        Offline workers are skipped entirely — their stale data is not
        useful and could mislead routing. The in-process BackendCatalog
        on the controller handles the local-host view; this method
        handles the remote-worker view.

        Returns:
            A dict with:
            - ``workers``: per-worker summary (name, status, capabilities,
              backend count, model count)
            - ``backends``: flat list of every remote backend entry with
              its owning worker tagged
            - ``capabilities``: set of capabilities present somewhere in
              the mesh (union across workers)
            - ``models``: flat list of every model loaded on any online
              worker, tagged with its owning worker and backend
        """
        workers_summary = []
        flat_backends: list[dict] = []
        flat_models: list[dict] = []
        all_capabilities: set[str] = set()

        for worker in self._workers.values():
            if worker.status != "online":
                continue

            worker_caps = set(worker.capabilities or [])
            all_capabilities |= worker_caps

            wbackends = worker.backends or []
            for b in wbackends:
                entry = {
                    **b,
                    "worker": worker.name,
                    "worker_url": worker.url,
                    "worker_platform": getattr(worker, "platform", ""),
                }
                flat_backends.append(entry)
                for m in b.get("models") or []:
                    flat_models.append({
                        **m,
                        "worker": worker.name,
                        "worker_url": worker.url,
                        "backend_name": b.get("name", ""),
                        "backend_type": b.get("type", ""),
                    })

            workers_summary.append({
                "name": worker.name,
                "url": worker.url,
                "platform": getattr(worker, "platform", ""),
                "status": worker.status,
                "load": worker.load,
                "capabilities": sorted(worker_caps),
                "backend_count": len(wbackends),
                "model_count": sum(len(b.get("models") or []) for b in wbackends),
            })

        return {
            "workers": workers_summary,
            "backends": flat_backends,
            "capabilities": sorted(all_capabilities),
            "models": flat_models,
        }

    async def _monitor_loop(self):
        """Monitor worker heartbeats, mark stale workers as offline."""
        while True:
            now = time.time()
            for worker in self._workers.values():
                if worker.status == "online" and (now - worker.last_heartbeat) > HEARTBEAT_TIMEOUT:
                    worker.status = "offline"
                    logger.warning(f"Worker '{worker.name}' marked offline (no heartbeat for {HEARTBEAT_TIMEOUT}s)")
                    if self._notifications:
                        await self._notifications.emit_event(
                            "worker.leave",
                            f"Worker '{worker.name}' went offline",
                            f"No heartbeat for {HEARTBEAT_TIMEOUT}s. Capabilities may be reduced.",
                            level="warning",
                        )
            await asyncio.sleep(5)
