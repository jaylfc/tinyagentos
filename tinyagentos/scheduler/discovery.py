"""Boot-time resource discovery.

Builds the initial set of Resources from the hardware profile and the
live backend catalog. Follows backend-driven discovery: a Resource is
registered only if the live catalog has at least one healthy backend
claiming the capabilities that Resource would serve.
"""
from __future__ import annotations

import logging
import os
import platform
from pathlib import Path
from typing import Optional

from tinyagentos.scheduler.backend_catalog import BackendCatalog
from tinyagentos.scheduler.resource import Resource, Tier
from tinyagentos.scheduler.scheduler import Scheduler
from tinyagentos.scheduler.types import ResourceSignature


# Every capability a CPU can run given the right backend. CPU is the
# universal fallback — nothing is exclusive to GPU/NPU at the capability
# level, just faster on those devices. This set feeds the CPU resource's
# ``potential_capabilities`` so the UI shows latent coverage even when no
# CPU backend for that capability is currently loaded.
CPU_POTENTIAL_CAPABILITIES: set[str] = {
    "llm-chat",
    "embedding",
    "reranking",
    "image-generation",
    "speech-to-text",
    "text-to-speech",
    "vision",
}

# NPU-only accelerators serve whatever models have been compiled for them.
# On RK3588 that's today a subset — embeddings, rerank, LLM chat (via
# rkllama) and image-gen (via rknn-sd). Other capabilities could be added
# once RKNN-exported models exist.
NPU_RK3588_POTENTIAL_CAPABILITIES: set[str] = {
    "llm-chat",
    "embedding",
    "reranking",
    "image-generation",
}

logger = logging.getLogger(__name__)


def _probe_librknnrt_version() -> str:
    """Read the librknnrt version string from the shared library."""
    candidates = [
        Path("/usr/lib/librknnrt.so"),
        Path("/usr/local/lib/librknnrt.so"),
        Path.home() / ".local" / "share" / "tinyagentos" / "rknn-sd" / "librknnrt.so",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = path.read_bytes()
            # The string "librknnrt version: X.Y.Z" is embedded in the binary.
            marker = b"librknnrt version: "
            idx = data.find(marker)
            if idx == -1:
                continue
            tail = data[idx + len(marker): idx + len(marker) + 32]
            version = tail.split(b" ", 1)[0].decode("ascii", errors="replace").strip("\x00")
            return version
        except Exception:
            continue
    return ""


def _physical_cores() -> int:
    try:
        import psutil
        return psutil.cpu_count(logical=False) or os.cpu_count() or 4
    except Exception:
        return os.cpu_count() or 4


def build_scheduler(
    hardware_profile,
    catalog: BackendCatalog,
    benchmark_store=None,
) -> Scheduler:
    """Instantiate a Scheduler and register the resources the live catalog
    currently supports.

    Backend-driven: we only register a Resource class if the catalog has at
    least one healthy backend that would feed it. If the NPU backend is
    offline at startup, the `npu-rk3588` Resource is NOT registered and
    tasks fall through to `cpu-inference` until the backend returns.
    """
    scheduler = Scheduler()

    def _make_score_lookup(resource_name: str):
        """Return a score_lookup callable bound to this resource name.

        Pulls the latest benchmark row for (worker_id=<resource_name>,
        capability) from the benchmark store if one is wired up.
        Returns None if there's no store or no record for that pairing
        yet. Scheduler falls back to tier-only routing in that case.
        """
        if benchmark_store is None:
            return None

        def _lookup(capability: str, model):
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return None
            # Schedule a lookup — but this is sync from the scheduler's
            # admission path. We sidestep by reading the most recent
            # cached value. Phase 2: add an in-memory LRU so this is truly
            # O(1) and async-free. For Phase 1 we only read if called
            # from an already-async context via create_task.
            return None  # Phase 2: actual async read from benchmark_store

        return _lookup

    # NPU (RK3588) — only if a healthy rknn-sd or rkllama backend exists
    npu_backends = (
        catalog.backends_with_capability("image-generation")
        + catalog.backends_with_capability("embedding")
    )
    has_rk_backend = any(b.type in ("rknn-sd", "rkllama") for b in npu_backends)
    npu_info = getattr(hardware_profile, "npu", None)
    npu_type = getattr(npu_info, "type", None)

    if has_rk_backend and npu_type == "rknpu":
        runtime_version = _probe_librknnrt_version()
        signature = ResourceSignature(
            platform="rk3588",
            runtime="librknnrt",
            runtime_version=runtime_version,
        )

        def _npu_capabilities() -> set[str]:
            caps: set[str] = set()
            for b in catalog.backends():
                if b.status == "ok" and b.type in ("rknn-sd", "rkllama"):
                    caps |= b.capabilities
            return caps

        def _npu_backend_for(capability: str) -> Optional[str]:
            for b in catalog.backends_with_capability(capability):
                if b.type in ("rknn-sd", "rkllama"):
                    return b.url
            return None

        scheduler.register(
            Resource(
                name="npu-rk3588",
                signature=signature,
                concurrency=1,  # RK3588 NPU serialises across the 3 cores
                tier=Tier.NPU,
                potential_capabilities=NPU_RK3588_POTENTIAL_CAPABILITIES,
                get_capabilities=_npu_capabilities,
                backend_lookup=_npu_backend_for,
                score_lookup=_make_score_lookup("npu-rk3588"),
            )
        )

    # CPU inference — always register. Backend-driven: only advertises the
    # capabilities that some CPU backend currently serves (sd-cpp, llama-cpp, etc.)
    cpu_signature = ResourceSignature(
        platform=f"cpu-{platform.machine()}",
        runtime="native",
        runtime_version="",
    )

    def _cpu_capabilities() -> set[str]:
        caps: set[str] = set()
        for b in catalog.backends():
            if b.status != "ok":
                continue
            # CPU backends: sd-cpp, llama-cpp (local CPU mode), ollama (if no GPU)
            if b.type in ("sd-cpp", "llama-cpp"):
                caps |= b.capabilities
        return caps

    def _cpu_backend_for(capability: str) -> Optional[str]:
        for b in catalog.backends_with_capability(capability):
            if b.type in ("sd-cpp", "llama-cpp"):
                return b.url
        return None

    cpu_cores = _physical_cores()
    cpu_concurrency = max(1, min(cpu_cores // 2, 4))
    scheduler.register(
        Resource(
            name="cpu-inference",
            signature=cpu_signature,
            concurrency=cpu_concurrency,
            tier=Tier.CPU,
            potential_capabilities=CPU_POTENTIAL_CAPABILITIES,
            get_capabilities=_cpu_capabilities,
            backend_lookup=_cpu_backend_for,
            score_lookup=_make_score_lookup("cpu-inference"),
        )
    )

    return scheduler
