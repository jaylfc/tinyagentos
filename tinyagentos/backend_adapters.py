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

_ADAPTERS: dict[str, BackendAdapter] = {
    "rkllama": OllamaCompatAdapter(),
    "ollama": OllamaCompatAdapter(),
    "llama-cpp": OpenAICompatAdapter(),
    "vllm": OpenAICompatAdapter(),
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
