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
        """Discover locally running inference backends via live probing.

        Backend-driven: each candidate gets a live health check and, on
        success, a live model list so the controller sees what's actually
        loaded right now. Filename conventions and static capability
        declarations are not the source of truth anywhere.
        """
        from tinyagentos.scheduler.backend_catalog import BACKEND_CAPABILITIES

        # Probe both the standard upstream ports AND the TAOS-namespaced
        # ones. install-worker.sh installs a TAOS-bundled Ollama on
        # 21434 to avoid colliding with any existing user Ollama on
        # 11434; we want to detect both so the user's pre-existing
        # backends are first-class citizens alongside the bundled one.
        candidates = [
            ("rkllama", "http://localhost:8080"),
            ("ollama", "http://localhost:11434"),         # user / system Ollama (default port)
            ("ollama", "http://localhost:21434"),         # TAOS-bundled Ollama (taos-ollama.service)
            ("llama-cpp", "http://localhost:8000"),
            ("llama-cpp", "http://localhost:18080"),      # TAOS-bundled llama.cpp (future)
            ("vllm", "http://localhost:8000"),
            ("vllm", "http://localhost:18000"),           # TAOS-bundled vLLM (future)
            ("sd-cpp", "http://localhost:7864"),
            ("rknn-sd", "http://localhost:7863"),
        ]

        backends = []
        async with httpx.AsyncClient(timeout=3) as client:
            for backend_type, base_url in candidates:
                models = await self._probe_models(client, backend_type, base_url)
                if models is None:
                    continue  # backend not running here
                kv_quant = await self._probe_kv_quant(client, backend_type, base_url)
                backends.append({
                    "name": f"{backend_type}@{base_url}",
                    "type": backend_type,
                    "url": base_url,
                    "capabilities": sorted(BACKEND_CAPABILITIES.get(backend_type, set())),
                    "models": models,
                    "status": "ok",
                    # Per-backend KV quant support, used by the worker to build
                    # its cluster-level kv_cache_quant_support advertisement.
                    "kv_quant_support": kv_quant,
                })
        return backends

    async def _probe_kv_quant(
        self, client: httpx.AsyncClient, backend_type: str, base_url: str
    ) -> list[str]:
        """Return the KV cache quantization types available on a backend.

        The probe is best-effort: any network error or unexpected response
        silently returns ["fp16"] so the cluster still gets a usable default.
        Image-generation backends (sd-cpp, rknn-sd) return an empty list
        because KV quant is not applicable to diffusion pipelines.

        When a backend (e.g. a future vLLM build with TurboQuant merged) starts
        reporting additional types, they appear here and flow up to the cluster-
        wide union without any other code changes.

        TODO: once vLLM upstream ships kv_cache_dtype support, replace the
        static ["fp16"] stub below with a live probe of GET /v1/info or a
        dedicated endpoint that the TurboQuant fork exposes.  Track in #144.
        """
        try:
            if backend_type in ("sd-cpp", "rknn-sd"):
                # Image-gen backends, KV quant is not applicable.
                return []
            if backend_type == "vllm":
                # vLLM exposes kv_cache_dtype in its model config.  Upstream
                # does not yet have a stable endpoint for enumerating supported
                # types; the TurboQuant fork will add one when it lands.  For
                # now we return ["fp16"] as the safe default.  When the
                # /v1/kv-quant-options or equivalent endpoint lands, replace
                # this block with a live GET and parse the response.
                return ["fp16"]
            if backend_type == "ollama":
                # Ollama wraps llama.cpp and does not yet expose KV quant
                # options externally.  Inherits whatever llama.cpp ships.
                return ["fp16"]
            if backend_type == "llama-cpp":
                # llama.cpp has its own Q-type scheme; TurboQuant-style KV
                # quantization has not landed upstream as of 2026-04.
                return ["fp16"]
            if backend_type in ("rkllama", "rknn-sd"):
                # rknn-toolkit does not expose KV cache quantization at the
                # Python API level.  Return the safe default.
                return ["fp16"]
            # Unknown backend type, default safe.
            return ["fp16"]
        except Exception:
            return ["fp16"]

    async def _probe_models(
        self, client: httpx.AsyncClient, backend_type: str, base_url: str
    ) -> list[dict] | None:
        """Ask a backend what models it has loaded. Returns None if the
        backend isn't reachable (not running on this host)."""
        try:
            if backend_type in ("rkllama", "ollama"):
                resp = await client.get(f"{base_url}/api/tags")
                if resp.status_code != 200:
                    return None
                data = resp.json()
                return [
                    {
                        "name": m.get("model") or m.get("name", ""),
                        "size_mb": (m.get("size") or 0) // 1_000_000,
                    }
                    for m in data.get("models", [])
                ]
            if backend_type == "sd-cpp":
                resp = await client.get(f"{base_url}/sdapi/v1/sd-models")
                if resp.status_code != 200:
                    return None
                return [
                    {"name": m.get("title") or m.get("model_name") or "", "size_mb": 0}
                    for m in (resp.json() if isinstance(resp.json(), list) else [])
                ]
            if backend_type == "rknn-sd":
                resp = await client.get(f"{base_url}/health")
                if resp.status_code != 200:
                    return None
                data = resp.json()
                name = data.get("model") or ""
                return [{"name": name, "size_mb": 0}] if name else []
            # llama-cpp / vllm, OpenAI compat /v1/models
            resp = await client.get(f"{base_url}/v1/models")
            if resp.status_code != 200:
                return None
            data = resp.json()
            return [
                {"name": m.get("id", ""), "size_mb": 0}
                for m in data.get("data", [])
            ]
        except Exception:
            return None

    def detect_kv_quant_support(self, backends: list[dict]) -> list[str]:
        """Union of KV cache quant types across all detected backends.

        Image-gen backends return [] (not applicable) and are skipped.  All
        LLM-capable backends contribute at minimum ["fp16"].  The result is
        sorted for stable serialisation.
        """
        quant_types: set[str] = set()
        for b in backends:
            per_backend = b.get("kv_quant_support")
            if per_backend is not None:
                quant_types.update(per_backend)
        # Always include fp16 as the baseline, a worker with no LLM backends
        # at all still defaults to fp16 for protocol compatibility.
        quant_types.add("fp16")
        return sorted(quant_types)

    def get_container_runtime(self) -> str | None:
        """Detect available container runtime (docker or podman). Returns None if neither found."""
        import shutil
        if shutil.which("docker"):
            return "docker"
        if shutil.which("podman"):
            return "podman"
        return None

    def supports_streaming(self) -> bool:
        """Return True if a container runtime is available for streaming apps."""
        return self.get_container_runtime() is not None

    def detect_capabilities(self, backends: list[dict]) -> list[str]:
        """Union of capabilities across all detected backends.

        Backend-driven: each backend contributes its own advertised
        capability set. Modern detect_backends() attaches the live set
        from BACKEND_CAPABILITIES on probe; a caller passing a legacy
        shape (only ``type`` on each dict) still works because we fall
        back to BACKEND_CAPABILITIES by type. Streaming is added if a
        container runtime is present.
        """
        from tinyagentos.scheduler.backend_catalog import BACKEND_CAPABILITIES

        caps: set[str] = set()
        for b in backends:
            declared = b.get("capabilities")
            if declared:
                caps.update(declared)
                continue
            btype = b.get("type")
            if btype:
                caps.update(BACKEND_CAPABILITIES.get(btype, set()))
        if self.supports_streaming():
            caps.add("app-streaming")
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
        kv_quant = self.detect_kv_quant_support(backends)

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
            "kv_cache_quant_support": kv_quant,
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

    async def heartbeat(self) -> int:
        """Send heartbeat to controller with live backend catalog.

        Backend-driven: the heartbeat carries a fresh probe of every
        detected backend, not a cached snapshot. This lets the controller
        aggregate per-worker catalogs into a cluster-wide view that
        reflects what's actually loaded right now across the mesh.

        Returns the HTTP status code from the controller, or 0 on
        connection failure / timeout. The caller uses this to detect
        the 404 case (controller restarted and forgot about us) and
        trigger a re-registration.
        """
        try:
            load = psutil.cpu_percent() / 100.0
            backends = await self.detect_backends()
            caps = self.detect_capabilities(backends)
            kv_quant = self.detect_kv_quant_support(backends)
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    f"{self.controller_url}/api/cluster/heartbeat",
                    json={
                        "name": self.name,
                        "load": load,
                        "backends": backends,
                        "capabilities": caps,
                        "kv_cache_quant_support": kv_quant,
                    },
                )
                return resp.status_code
        except Exception:
            return 0

    async def run(self):
        """Main worker loop, register, heartbeat, re-register on loss.

        The controller's in-memory cluster registry is wiped on every
        controller restart. When that happens our heartbeats start
        coming back as 404 'Worker not registered'. Treat that as a
        signal to re-register and resume, without it, every controller
        restart leaves the cluster view empty until the worker is
        manually restarted.
        """
        self._running = True
        while self._running:
            # Register if we aren't (yet, or any more).
            if not self._registered:
                if await self.register():
                    logger.info(f"worker '{self.name}' registered with {self.controller_url}")
                else:
                    await asyncio.sleep(5)
                    continue

            status = await self.heartbeat()
            if status == 404:
                # Controller has forgotten about us (restart, manual
                # deregister, etc). Drop our registered state and the
                # next loop iteration will re-register.
                logger.warning(
                    f"controller returned 404 on heartbeat, re-registering '{self.name}'"
                )
                self._registered = False
            elif status == 0:
                # Network / DNS / controller-down. Don't drop the
                # registered flag yet; the controller may still know
                # us when it comes back. Just retry on next tick.
                pass
            await asyncio.sleep(5)

    def stop(self):
        self._running = False
