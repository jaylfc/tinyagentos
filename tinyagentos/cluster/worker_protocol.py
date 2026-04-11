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
