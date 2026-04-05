from __future__ import annotations
import logging
import httpx
from tinyagentos.cluster.manager import ClusterManager

logger = logging.getLogger(__name__)


class TaskRouter:
    """Routes inference requests to the best available worker."""

    def __init__(self, cluster: ClusterManager, http_client: httpx.AsyncClient):
        self.cluster = cluster
        self.http_client = http_client

    async def route_request(self, capability: str, method: str, path: str,
                            body: dict | None = None, timeout: float = 60) -> tuple[dict | None, str | None]:
        """Route a request to the best worker for the given capability.
        Returns (response_data, worker_name) or (None, None) if all fail.
        """
        workers = self.cluster.get_workers_for_capability(capability)

        for worker in workers:
            try:
                url = f"{worker.url.rstrip('/')}{path}"
                if method == "GET":
                    resp = await self.http_client.get(url, timeout=timeout)
                else:
                    resp = await self.http_client.post(url, json=body, timeout=timeout)
                resp.raise_for_status()
                return resp.json(), worker.name
            except Exception as e:
                logger.warning(f"Worker '{worker.name}' failed for {capability}: {e}")
                continue

        return None, None

    async def embed(self, text: str) -> tuple[dict | None, str | None]:
        return await self.route_request("embed", "POST", "/embed", {"text": text})

    async def chat(self, messages: list[dict], model: str | None = None) -> tuple[dict | None, str | None]:
        body = {"messages": messages}
        if model:
            body["model"] = model
        return await self.route_request("chat", "POST", "/v1/chat/completions", body)

    async def generate_image(self, prompt: str, **kwargs) -> tuple[dict | None, str | None]:
        body = {"prompt": prompt, **kwargs}
        return await self.route_request("image-generation", "POST", "/v1/images/generations", body, timeout=120)
