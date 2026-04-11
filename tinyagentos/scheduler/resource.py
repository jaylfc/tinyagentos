"""Resource — one physical accelerator (or CPU pool) that runs Tasks.

A Resource is an async singleton with a concurrency semaphore, a signature
declaring its platform/runtime/version, and a set of capabilities derived
from the backends currently pointing at it. It does NOT own a queue in
Phase 1 — the Scheduler calls ``Resource.run(task)`` directly with the
semaphore providing mutual exclusion.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

import psutil

from tinyagentos.scheduler.types import ResourceSignature, Task

logger = logging.getLogger(__name__)


class Resource:
    """An accelerator or CPU pool. One instance per physical device.

    Args:
        name: stable id — "npu-rk3588", "cpu-inference", "gpu-cuda-0", ...
        signature: runtime identity for admission matching
        concurrency: how many Tasks can run in parallel
        memory_probe: optional callable returning available RAM in MB
        get_capabilities: callable returning the current set of capabilities
                          this resource can serve, derived from the live
                          backend catalog (backend-driven discovery)
        backend_lookup: callable that returns the live backend URL for a
                        given capability — used by payloads that need to
                        know where to POST the actual request
    """

    def __init__(
        self,
        name: str,
        signature: ResourceSignature,
        concurrency: int,
        get_capabilities: Callable[[], set[str]],
        backend_lookup: Callable[[str], Optional[str]],
        memory_probe: Optional[Callable[[], int]] = None,
    ):
        self.name = name
        self.signature = signature
        self.concurrency = concurrency
        self._semaphore = asyncio.Semaphore(concurrency)
        self._in_flight = 0
        self._get_capabilities = get_capabilities
        self._backend_lookup = backend_lookup
        self._memory_probe = memory_probe or _default_memory_probe

    @property
    def capabilities(self) -> set[str]:
        """Live set of capabilities this resource can currently serve.

        Backend-driven: answers by asking the catalog, not from a static field.
        """
        return self._get_capabilities()

    @property
    def in_flight(self) -> int:
        return self._in_flight

    def backend_url_for(self, capability: str) -> Optional[str]:
        """Look up the backend URL this resource uses for a given capability."""
        return self._backend_lookup(capability)

    def can_admit(self, task: Task) -> tuple[bool, Optional[str]]:
        """Check whether this resource can take a task right now.

        Returns ``(True, None)`` if yes, ``(False, reason)`` if not.
        """
        caps = self.capabilities
        if task.capability.value not in caps:
            return False, f"capability '{task.capability.value}' not served by {self.name}"
        for req in task.required_signatures:
            if not self.signature.matches(req):
                return False, (
                    f"signature mismatch: {self.name} is "
                    f"{self.signature.platform}/{self.signature.runtime}/{self.signature.runtime_version}, "
                    f"task requires {req.platform}/{req.runtime}/{req.runtime_version}"
                )
        if self._in_flight >= self.concurrency:
            return False, f"{self.name} is at concurrency cap ({self.concurrency})"
        if task.estimated_memory_mb > 0:
            avail = self._memory_probe()
            if avail < task.estimated_memory_mb + 1024:
                return False, (
                    f"insufficient memory on {self.name}: "
                    f"need {task.estimated_memory_mb} MB + 1024 MB headroom, "
                    f"have {avail} MB"
                )
        return True, None

    async def run(self, task: Task) -> tuple[object, float]:
        """Acquire the semaphore and run the task payload.

        Returns ``(result, elapsed_seconds)``. Exceptions propagate.
        """
        async with self._semaphore:
            self._in_flight += 1
            start = time.monotonic()
            try:
                result = await task.payload(self)
                elapsed = time.monotonic() - start
                return result, elapsed
            finally:
                self._in_flight -= 1


def _default_memory_probe() -> int:
    """Available RAM in MB."""
    try:
        return psutil.virtual_memory().available // (1024 * 1024)
    except Exception:
        return 999_999  # don't block on probe failure
