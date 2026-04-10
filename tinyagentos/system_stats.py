"""Live system resource stats: NPU and VRAM usage helpers.

CPU and RAM are read directly from psutil in the caller; this module
focuses on accelerators whose stats require hardware-specific probes.

All helpers return ``None`` when data is unavailable, so callers can
pass the value straight through JSON and let the frontend hide the
indicator.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_RKNPU_LOAD_PATHS = (
    "/sys/kernel/debug/rknpu/load",
    "/sys/class/devfreq/fdab0000.npu/load",
)


def read_rknpu_load() -> float | None:
    """Return RK3588 NPU load as a percentage (0-100) or None.

    The rknpu debugfs entry typically looks like::

        NPU load:  Core0:  12%, Core1:   0%, Core2:   0%,

    We average the cores we can parse.
    """
    for path in _RKNPU_LOAD_PATHS:
        try:
            raw = Path(path).read_text()
        except (FileNotFoundError, PermissionError, OSError):
            continue
        pcts: list[float] = []
        for token in raw.replace(",", " ").split():
            if token.endswith("%"):
                try:
                    pcts.append(float(token.rstrip("%")))
                except ValueError:
                    pass
        if pcts:
            return sum(pcts) / len(pcts)
    return None


def read_nvidia_vram() -> tuple[int, int] | None:
    """Return (used_mb, total_mb) for the first NVIDIA GPU, or None."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    if out.returncode != 0:
        return None
    line = out.stdout.strip().splitlines()[:1]
    if not line:
        return None
    try:
        used_str, total_str = [p.strip() for p in line[0].split(",", 1)]
        return int(used_str), int(total_str)
    except (ValueError, IndexError):
        return None


def read_nvidia_gpu_load() -> float | None:
    """Return NVIDIA GPU utilisation as a percentage, or None."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    if out.returncode != 0:
        return None
    line = out.stdout.strip().splitlines()[:1]
    if not line:
        return None
    try:
        return float(line[0].strip())
    except ValueError:
        return None


def get_npu_usage(npu_type: str) -> float | None:
    """Dispatch to the right NPU load reader based on detected hardware."""
    if npu_type == "rknpu":
        return read_rknpu_load()
    return None


def get_vram_usage(gpu_type: str) -> tuple[float | None, int | None, int | None]:
    """Return (percent, used_mb, total_mb) for the given GPU type.

    Falls back to ``(None, None, None)`` when unavailable.
    """
    if gpu_type == "nvidia":
        pair = read_nvidia_vram()
        if pair is None:
            return None, None, None
        used_mb, total_mb = pair
        pct = (used_mb / total_mb * 100.0) if total_mb else None
        return pct, used_mb, total_mb
    return None, None, None
