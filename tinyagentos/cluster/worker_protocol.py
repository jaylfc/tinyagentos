from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class WorkerInfo:
    name: str
    url: str                          # Worker's base URL
    hardware: dict = field(default_factory=dict)  # From hardware detection
    backends: list[dict] = field(default_factory=list)  # Available inference backends
    models: list[str] = field(default_factory=list)     # Currently loaded models
    capabilities: list[str] = field(default_factory=list)  # embed, chat, rerank, image-gen, tts, etc
    status: str = "online"            # online | offline | busy
    last_heartbeat: float = 0
    registered_at: float = 0
    load: float = 0.0                 # 0-1 utilization estimate
    platform: str = ""                # linux | windows | macos
    tier_id: str = ""                 # catalog hardware tier, e.g. "x86-cuda-12gb"
    potential_capabilities: list[str] = field(default_factory=list)  # derived from catalog + tier
    # KV cache quantization types this worker can serve.  Defaults to ["fp16"]
    # so old workers that pre-date this field are treated as fp16-only.  A
    # worker running a TurboQuant-capable vLLM build will probe its backends at
    # startup and report additional entries here, e.g. ["fp16", "turboquant-k3v2"].
    # The controller unions these across all online workers and exposes the
    # result via /api/cluster/kv-quant-options so the deploy wizard can show a
    # dropdown only when there is actually something to choose from.
    kv_cache_quant_support: list[str] = field(default_factory=lambda: ["fp16"])
