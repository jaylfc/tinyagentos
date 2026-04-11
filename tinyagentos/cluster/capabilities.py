"""Helpers to derive potential capabilities from worker hardware and the app catalog.

The catalog manifests (app-catalog/models/*/manifest.yaml) declare
``hardware_tiers`` keys like ``x86-cuda-12gb``.  For GPU-accelerated tiers
(cuda / rocm) the ``{n}gb`` suffix is VRAM; for every other accelerator
type (cpu, npu, vulkan, apple-silicon) it is system RAM.  This mirrors
the logic in ``HardwareProfile.profile_id`` with one correction: CUDA/ROCm
tiers use VRAM so that a 64 GB RAM machine with a 12 GB RTX 3060 maps to
``x86-cuda-12gb``, not ``x86-cuda-64gb``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tinyagentos.registry import AppRegistry


def worker_tier_id(hardware: dict) -> str:
    """Derive a catalog-compatible tier id from a worker's hardware dict.

    Parameters
    ----------
    hardware:
        The ``hardware`` dict stored on a :class:`~tinyagentos.cluster.worker_protocol.WorkerInfo`
        (originally reported by the worker agent via ``/api/cluster/workers``).

    Returns
    -------
    str
        A tier id like ``x86-cuda-12gb`` or ``arm-npu-16gb``.
    """
    if not hardware:
        return "cpu-only"

    cpu_raw = hardware.get("cpu") or {}
    # Guard: workers running older agent versions may send cpu as a plain string
    cpu: dict = cpu_raw if isinstance(cpu_raw, dict) else {}
    arch_raw = cpu.get("arch", "")
    arch = "arm" if arch_raw in ("aarch64", "armv7l", "arm64") else "x86"

    gpu = hardware.get("gpu") or {}
    npu = hardware.get("npu") or {}
    ram_mb = hardware.get("ram_mb", 0)

    gpu_type = gpu.get("type", "none") or "none"
    npu_type = npu.get("type", "none") or "none"

    # Determine accelerator class
    if npu_type != "none":
        accel = "npu"
        # NPU tiers use RAM gb
        gb = max(1, ram_mb // 1024)
        return f"{arch}-{accel}-{gb}gb"

    if gpu_type == "nvidia" and gpu.get("cuda"):
        accel = "cuda"
        vram_mb = gpu.get("vram_mb", 0) or 0
        gb = max(1, vram_mb // 1024) if vram_mb else max(1, ram_mb // 1024)
        return f"{arch}-{accel}-{gb}gb"

    if gpu_type == "amd" and gpu.get("rocm"):
        accel = "rocm"
        vram_mb = gpu.get("vram_mb", 0) or 0
        gb = max(1, vram_mb // 1024) if vram_mb else max(1, ram_mb // 1024)
        return f"{arch}-{accel}-{gb}gb"

    if gpu_type == "apple":
        # Apple Silicon — unified memory; a single tier covers all M-series
        return "apple-silicon"

    if gpu.get("vulkan"):
        accel = "vulkan"
        vram_mb = gpu.get("vram_mb", 0) or 0
        gb = max(1, vram_mb // 1024) if vram_mb else max(1, ram_mb // 1024)
        return f"{arch}-{accel}-{gb}gb"

    # CPU-only fallback
    gb = max(1, ram_mb // 1024)
    return f"{arch}-cpu-{gb}gb"


def potential_capabilities(hardware: dict, registry: "AppRegistry") -> tuple[str, list[str]]:
    """Return the tier id and list of capabilities the hardware *could* support.

    Walks every model in the catalog and collects the distinct capability
    strings from any manifest that declares the worker's tier as compatible
    (i.e. has a non-``unsupported`` / non-null entry for that tier).

    Parameters
    ----------
    hardware:
        Worker hardware dict.
    registry:
        The loaded :class:`~tinyagentos.registry.AppRegistry` with all
        manifests already parsed.

    Returns
    -------
    tuple[str, list[str]]
        ``(tier_id, sorted_unique_capabilities)``
    """
    tier_id = worker_tier_id(hardware)
    caps: set[str] = set()

    for manifest in registry.list_available(type_filter="model"):
        tiers = manifest.hardware_tiers or {}
        tier_val = tiers.get(tier_id)
        if tier_val is None:
            continue
        compatible = False
        if isinstance(tier_val, str):
            compatible = tier_val != "unsupported"
        elif isinstance(tier_val, dict):
            compatible = (
                tier_val.get("recommended") is not None
                or tier_val.get("fallback") is not None
            )
        if compatible:
            caps.update(manifest.capabilities or [])

    return tier_id, sorted(caps)
