"""LiteLLM proxy management — hidden internal LLM gateway."""
from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Map TinyAgentOS backend types to LiteLLM model prefixes
BACKEND_TYPE_MAP = {
    "ollama": "ollama_chat",
    "rkllama": "ollama_chat",  # rkllama is ollama-compatible
    "llama-cpp": "openai",
    "vllm": "openai",
    "exo": "openai",
    "mlx": "openai",
    "openai": "openai",
    "anthropic": "anthropic",
}


def generate_litellm_config(backends: list[dict], default_model: str = "default") -> dict:
    """Generate LiteLLM config from TinyAgentOS backend list."""
    model_list = []
    sorted_backends = sorted(backends, key=lambda b: b.get("priority", 99))

    for backend in sorted_backends:
        backend_type = backend.get("type", "ollama")
        prefix = BACKEND_TYPE_MAP.get(backend_type, "openai")
        url = backend.get("url", "").rstrip("/")
        model_name = backend.get("model", "default")

        litellm_params = {
            "model": f"{prefix}/{model_name}",
        }

        # Set api_base for local/self-hosted backends
        if backend_type in ("ollama", "rkllama", "llama-cpp", "vllm", "exo", "mlx"):
            litellm_params["api_base"] = url

        # API key from secrets reference
        if backend.get("api_key_secret"):
            litellm_params["api_key"] = f"os.environ/{backend['api_key_secret']}"
        elif backend.get("api_key"):
            litellm_params["api_key"] = backend["api_key"]

        model_list.append({
            "model_name": default_model,
            "litellm_params": litellm_params,
            "metadata": {
                "priority": backend.get("priority", 99),
                "backend_name": backend.get("name", ""),
            },
        })

    return {
        "model_list": model_list,
        "router_settings": {
            "routing_strategy": "latency-based-routing",
            "num_retries": 2,
            "timeout": 120,
        },
    }


class LLMProxy:
    """Manages LiteLLM proxy as a subprocess."""

    def __init__(self, port: int = 4000, config_dir: Path | None = None):
        self.port = port
        self.config_dir = config_dir or Path("/tmp/taos-litellm")
        self._process: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}"

    def is_running(self) -> bool:
        if not self._process:
            return False
        return self._process.poll() is None

    def write_config(self, backends: list[dict]) -> Path:
        """Generate and write LiteLLM config file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        config = generate_litellm_config(backends)
        config_path = self.config_dir / "litellm_config.yaml"

        import yaml
        config_path.write_text(yaml.dump(config, default_flow_style=False))
        return config_path

    async def start(self, backends: list[dict]) -> bool:
        """Start LiteLLM proxy with auto-generated config."""
        if self.is_running():
            return True

        config_path = self.write_config(backends)

        try:
            self._process = subprocess.Popen(
                [
                    "litellm",
                    "--config", str(config_path),
                    "--port", str(self.port),
                    "--host", "127.0.0.1",
                    "--detailed_debug",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Wait for startup
            for _ in range(30):
                await asyncio.sleep(1)
                try:
                    async with httpx.AsyncClient(timeout=3) as client:
                        resp = await client.get(f"{self.url}/health")
                        if resp.status_code == 200:
                            logger.info(f"LiteLLM proxy started on port {self.port}")
                            return True
                except Exception:
                    pass
            logger.error("LiteLLM proxy failed to start within 30s")
            return False
        except FileNotFoundError:
            logger.warning("LiteLLM not installed — proxy disabled. Install with: pip install litellm[proxy]")
            return False

    def stop(self):
        """Stop the LiteLLM proxy."""
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
            logger.info("LiteLLM proxy stopped")

    async def create_agent_key(self, agent_name: str, models: list[str] | None = None,
                                max_budget: float | None = None) -> str | None:
        """Create a per-agent virtual key via LiteLLM API."""
        if not self.is_running():
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                body = {
                    "key_alias": f"taos-{agent_name}",
                    "models": models or ["default"],
                    "metadata": {"agent": agent_name, "managed_by": "tinyagentos"},
                }
                if max_budget is not None:
                    body["max_budget"] = max_budget
                resp = await client.post(f"{self.url}/key/generate", json=body,
                                          headers={"Authorization": "Bearer sk-taos-master"})
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("key", data.get("token"))
        except Exception as e:
            logger.warning(f"Failed to create LiteLLM key for {agent_name}: {e}")
        return None

    async def delete_agent_key(self, key: str) -> bool:
        """Delete a per-agent virtual key."""
        if not self.is_running():
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{self.url}/key/delete", json={"keys": [key]},
                                          headers={"Authorization": "Bearer sk-taos-master"})
                return resp.status_code == 200
        except Exception:
            return False

    async def get_key_usage(self, key: str) -> dict | None:
        """Get usage stats for an agent's key."""
        if not self.is_running():
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.url}/key/info", params={"key": key},
                                         headers={"Authorization": "Bearer sk-taos-master"})
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass
        return None
