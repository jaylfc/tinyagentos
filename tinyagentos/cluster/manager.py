from __future__ import annotations
import asyncio
import logging
import time
from tinyagentos.cluster.worker_protocol import WorkerInfo

logger = logging.getLogger(__name__)

HEARTBEAT_TIMEOUT = 30  # seconds before marking worker offline


class ClusterManager:
    def __init__(self):
        self._workers: dict[str, WorkerInfo] = {}
        self._monitor_task: asyncio.Task | None = None

    async def start(self):
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self):
        if self._monitor_task:
            self._monitor_task.cancel()

    def register_worker(self, info: WorkerInfo) -> None:
        info.registered_at = time.time()
        info.last_heartbeat = time.time()
        info.status = "online"
        self._workers[info.name] = info
        logger.info(f"Worker registered: {info.name} ({info.platform}, {len(info.capabilities)} capabilities)")

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
            await asyncio.sleep(5)
