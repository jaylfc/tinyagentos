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

            await self._notifications.add(
                f"Worker '{info.name}' joined the cluster",
                msg,
                level="info",
                source="cluster",
            )

    def heartbeat(self, name: str, load: float = 0.0, models: list[str] | None = None) -> bool:
        worker = self._workers.get(name)
        if not worker:
            return False
        worker.last_heartbeat = time.time()
        worker.load = load
        worker.status = "online"
        if models is not None:
            worker.models = models
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

    async def _monitor_loop(self):
        """Monitor worker heartbeats, mark stale workers as offline."""
        while True:
            now = time.time()
            for worker in self._workers.values():
                if worker.status == "online" and (now - worker.last_heartbeat) > HEARTBEAT_TIMEOUT:
                    worker.status = "offline"
                    logger.warning(f"Worker '{worker.name}' marked offline (no heartbeat for {HEARTBEAT_TIMEOUT}s)")
                    if self._notifications:
                        await self._notifications.add(
                            f"Worker '{worker.name}' went offline",
                            f"No heartbeat for {HEARTBEAT_TIMEOUT}s. Capabilities may be reduced.",
                            level="warning",
                            source="cluster",
                        )
            await asyncio.sleep(5)
