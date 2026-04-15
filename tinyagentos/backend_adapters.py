from __future__ import annotations

import time
from abc import ABC, abstractmethod

import httpx


class BackendAdapter(ABC):
    @abstractmethod
    async def health(self, client: httpx.AsyncClient, url: str) -> dict:
        ...


class OllamaCompatAdapter(BackendAdapter):
    """Adapter for Ollama-compatible APIs (rkllama, ollama).

    Uses GET /api/tags to list models and check health.
    """

    async def health(self, client: httpx.AsyncClient, url: str) -> dict:
        start = time.monotonic()
        try:
            resp = await client.get(f"{url.rstrip('/')}/api/tags", timeout=10)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            resp.raise_for_status()
            data = resp.json()
            models = [
                {"name": m.get("name", ""), "size_mb": m.get("size", 0) // 1_000_000}
                for m in data.get("models", [])
            ]
            return {"status": "ok", "response_ms": elapsed_ms, "models": models}
        except Exception:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {"status": "error", "response_ms": elapsed_ms, "models": []}


class RknnSdAdapter(BackendAdapter):
    """Adapter for the darkbit1001-style RKNN Stable Diffusion server.

    Exposes POST /generate returning a raw image/png body. Health is proven
    by the presence of /openapi.json (the server uses no explicit /health).
    """

    async def health(self, client: httpx.AsyncClient, url: str) -> dict:
        start = time.monotonic()
        base = url.rstrip("/")
        try:
            resp = await client.get(f"{base}/openapi.json", timeout=10)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            resp.raise_for_status()
            return {
                "status": "ok",
                "response_ms": elapsed_ms,
                "models": [{"name": "lcm-dreamshaper-v7-rknn", "size_mb": 0}],
            }
        except Exception:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {"status": "error", "response_ms": elapsed_ms, "models": []}


class StableDiffusionCppAdapter(BackendAdapter):
    """Adapter for leejet/stable-diffusion.cpp sd-server.

    sd-server exposes an A1111-compatible /sdapi/v1/txt2img endpoint and no
    /health or /v1/models. We probe /sdapi/v1/options and /sdapi/v1/sd-models
    to confirm it's alive and list loaded weights.
    """

    async def health(self, client: httpx.AsyncClient, url: str) -> dict:
        start = time.monotonic()
        base = url.rstrip("/")
        try:
            # Probe /sdapi/v1/options — responds even with no model loaded.
            resp = await client.get(f"{base}/sdapi/v1/options", timeout=10)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            resp.raise_for_status()
        except Exception:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {"status": "error", "response_ms": elapsed_ms, "models": []}

        # Server is alive — fetch model list best-effort; empty list is fine.
        models = []
        try:
            mr = await client.get(f"{base}/sdapi/v1/sd-models", timeout=10)
            if mr.status_code == 200:
                data = mr.json()
                models = [
                    {"name": m.get("title", m.get("model_name", "")), "size_mb": 0}
                    for m in (data if isinstance(data, list) else [])
                ]
        except Exception:
            pass

        return {"status": "ok", "response_ms": elapsed_ms, "models": models}


class OpenAICompatAdapter(BackendAdapter):
    """Adapter for OpenAI-compatible APIs (llama.cpp, vLLM).

    Uses GET /health for status, GET /v1/models for model list.
    """

    async def health(self, client: httpx.AsyncClient, url: str) -> dict:
        start = time.monotonic()
        base = url.rstrip("/")
        try:
            resp = await client.get(f"{base}/health", timeout=10)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            resp.raise_for_status()
            models = []
            try:
                model_resp = await client.get(f"{base}/v1/models", timeout=10)
                if model_resp.status_code == 200:
                    models = [
                        {"name": m.get("id", ""), "size_mb": 0}
                        for m in model_resp.json().get("data", [])
                    ]
            except Exception:
                pass
            return {"status": "ok", "response_ms": elapsed_ms, "models": models}
        except Exception:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {"status": "error", "response_ms": elapsed_ms, "models": []}


# Type aliases for backwards compatibility with tests
RkLlamaAdapter = OllamaCompatAdapter
OllamaAdapter = OllamaCompatAdapter
LlamaCppAdapter = OpenAICompatAdapter
VllmAdapter = OpenAICompatAdapter

ExoAdapter = OpenAICompatAdapter  # Exo exposes OpenAI-compatible API

_ADAPTERS: dict[str, BackendAdapter] = {
    "rkllama": OllamaCompatAdapter(),
    "ollama": OllamaCompatAdapter(),
    "llama-cpp": OpenAICompatAdapter(),
    "vllm": OpenAICompatAdapter(),
    "exo": OpenAICompatAdapter(),  # Exo distributed inference — OpenAI-compatible API
    "mlx": OpenAICompatAdapter(),  # MLX via mlx-lm server — OpenAI-compatible
    "openai": OpenAICompatAdapter(),  # OpenAI API
    "anthropic": OpenAICompatAdapter(),  # Anthropic API (health check via OpenAI-compat endpoint)
    "sd-cpp": StableDiffusionCppAdapter(),  # leejet/stable-diffusion.cpp sd-server
    "rknn-sd": RknnSdAdapter(),  # darkbit1001 LCM Dreamshaper on RK3588 NPU
}


def get_adapter(backend_type: str) -> BackendAdapter:
    adapter = _ADAPTERS.get(backend_type)
    if not adapter:
        raise ValueError(f"Unknown backend type: '{backend_type}'")
    return adapter


async def check_backend_health(client: httpx.AsyncClient, backend: dict) -> dict:
    adapter = get_adapter(backend["type"])
    result = await adapter.health(client, backend["url"])
    return {**result, "name": backend["name"], "type": backend["type"], "priority": backend.get("priority", 99)}
