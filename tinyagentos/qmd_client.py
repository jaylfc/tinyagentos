from __future__ import annotations

import time

import httpx

from tinyagentos.clients.retry import with_retry


class QmdClient:
    """HTTP client for qmd serve API."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def init(self) -> None:
        self._client = httpx.AsyncClient(timeout=60)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def embed(self, text: str) -> list[float]:
        """Get embedding vector for text via qmd serve /embed."""
        url = f"{self.base_url}/embed"
        client = self._client

        async def _call():
            resp = await client.post(url, json={"text": text})
            resp.raise_for_status()
            return resp

        resp = await with_retry(_call)
        return resp.json()["embedding"]

    async def health(self) -> dict:
        """Check qmd serve health."""
        start = time.monotonic()
        try:
            resp = await self._client.get(f"{self.base_url}/health", timeout=10)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            resp.raise_for_status()
            data = resp.json()
            return {**data, "response_ms": elapsed_ms}
        except (httpx.HTTPError, Exception):
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {"status": "error", "response_ms": elapsed_ms}
