from __future__ import annotations
import asyncio
import logging
import platform
import socket
import time
import httpx
import psutil

logger = logging.getLogger(__name__)


class WorkerAgent:
    def __init__(self, controller_url: str, name: str | None = None, worker_port: int = 0):
        self.controller_url = controller_url.rstrip("/")
        self.name = name or socket.gethostname()
        self.worker_port = worker_port
        self._running = False
        self._registered = False

    async def detect_backends(self) -> list[dict]:
        """Discover locally running inference backends."""
        backends = []
        checks = [
            ("ollama", "http://localhost:11434", "/api/tags"),
            ("rkllama", "http://localhost:8080", "/api/tags"),
            ("llama-cpp", "http://localhost:8080", "/health"),
            ("vllm", "http://localhost:8000", "/health"),
        ]
        async with httpx.AsyncClient(timeout=3) as client:
            for backend_type, base_url, health_path in checks:
                try:
                    resp = await client.get(base_url + health_path)
                    if resp.status_code == 200:
                        backends.append({
                            "type": backend_type,
                            "url": base_url,
                        })
                except Exception:
                    pass
        return backends

    def detect_capabilities(self, backends: list[dict]) -> list[str]:
        """Determine capabilities from detected backends."""
        caps = set()
        for b in backends:
            if b["type"] in ("ollama", "rkllama", "llama-cpp", "vllm"):
                caps.update(["chat", "embed"])
            if b["type"] in ("rkllama", "ollama"):
                caps.add("image-generation")
            if b["type"] in ("rkllama",):
                caps.add("rerank")
        return sorted(caps)

    def get_worker_url(self) -> str:
        """Get this worker's reachable URL."""
        # Try to get LAN IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            ip = "127.0.0.1"
        return f"http://{ip}:{self.worker_port}" if self.worker_port else f"http://{ip}"

    async def register(self) -> bool:
        """Register with the controller."""
        from tinyagentos.hardware import detect_hardware
        from dataclasses import asdict

        hw = detect_hardware()
        backends = await self.detect_backends()
        caps = self.detect_capabilities(backends)

        # Find the actual backend URL to use (first discovered)
        worker_url = backends[0]["url"] if backends else self.get_worker_url()

        payload = {
            "name": self.name,
            "url": worker_url,
            "hardware": asdict(hw),
            "backends": backends,
            "capabilities": caps,
            "platform": platform.system().lower(),
            "models": [],
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{self.controller_url}/api/cluster/workers", json=payload)
                resp.raise_for_status()
                self._registered = True
                logger.info(f"Registered with controller as '{self.name}'")
                return True
        except Exception as e:
            logger.error(f"Failed to register: {e}")
            return False

    async def heartbeat(self) -> bool:
        """Send heartbeat to controller."""
        try:
            load = psutil.cpu_percent() / 100.0
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    f"{self.controller_url}/api/cluster/heartbeat",
                    json={"name": self.name, "load": load},
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def run(self):
        """Main worker loop — register then heartbeat."""
        self._running = True
        # Register
        while self._running and not self._registered:
            if await self.register():
                break
            await asyncio.sleep(5)

        # Heartbeat loop
        while self._running:
            await self.heartbeat()
            await asyncio.sleep(5)

    def stop(self):
        self._running = False
