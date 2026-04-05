from __future__ import annotations
import time
from abc import ABC, abstractmethod
import httpx

class BackendAdapter(ABC):
    @abstractmethod
    async def health(self, client: httpx.AsyncClient, url: str) -> dict:
        ...

class RkLlamaAdapter(BackendAdapter):
    async def health(self, client: httpx.AsyncClient, url: str) -> dict:
        start = time.monotonic()
        try:
            resp = await client.get(f"{url.rstrip('/')}/api/tags", timeout=10)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            resp.raise_for_status()
            data = resp.json()
            models = [{"name": m.get("name", ""), "size_mb": m.get("size", 0) // 1_000_000} for m in data.get("models", [])]
            return {"status": "ok", "response_ms": elapsed_ms, "models": models}
        except (httpx.HTTPError, Exception):
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {"status": "error", "response_ms": elapsed_ms, "models": []}

class OllamaAdapter(BackendAdapter):
    async def health(self, client: httpx.AsyncClient, url: str) -> dict:
        start = time.monotonic()
        try:
            resp = await client.get(f"{url.rstrip('/')}/api/tags", timeout=10)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            resp.raise_for_status()
            data = resp.json()
            models = [{"name": m.get("name", ""), "size_mb": m.get("size", 0) // 1_000_000} for m in data.get("models", [])]
            return {"status": "ok", "response_ms": elapsed_ms, "models": models}
        except (httpx.HTTPError, Exception):
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {"status": "error", "response_ms": elapsed_ms, "models": []}

class LlamaCppAdapter(BackendAdapter):
    async def health(self, client: httpx.AsyncClient, url: str) -> dict:
        start = time.monotonic()
        try:
            resp = await client.get(f"{url.rstrip('/')}/health", timeout=10)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            resp.raise_for_status()
            models = []
            try:
                model_resp = await client.get(f"{url.rstrip('/')}/v1/models", timeout=10)
                if model_resp.status_code == 200:
                    model_data = model_resp.json()
                    models = [{"name": m.get("id", ""), "size_mb": 0} for m in model_data.get("data", [])]
            except (httpx.HTTPError, Exception):
                pass
            return {"status": "ok", "response_ms": elapsed_ms, "models": models}
        except (httpx.HTTPError, Exception):
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {"status": "error", "response_ms": elapsed_ms, "models": []}

class VllmAdapter(BackendAdapter):
    async def health(self, client: httpx.AsyncClient, url: str) -> dict:
        start = time.monotonic()
        try:
            resp = await client.get(f"{url.rstrip('/')}/health", timeout=10)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            resp.raise_for_status()
            models = []
            try:
                model_resp = await client.get(f"{url.rstrip('/')}/v1/models", timeout=10)
                if model_resp.status_code == 200:
                    model_data = model_resp.json()
                    models = [{"name": m.get("id", ""), "size_mb": 0} for m in model_data.get("data", [])]
            except (httpx.HTTPError, Exception):
                pass
            return {"status": "ok", "response_ms": elapsed_ms, "models": models}
        except (httpx.HTTPError, Exception):
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {"status": "error", "response_ms": elapsed_ms, "models": []}

_ADAPTERS: dict[str, BackendAdapter] = {
    "rkllama": RkLlamaAdapter(),
    "ollama": OllamaAdapter(),
    "llama-cpp": LlamaCppAdapter(),
    "vllm": VllmAdapter(),
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
