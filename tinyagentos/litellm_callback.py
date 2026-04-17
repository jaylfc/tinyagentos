"""LiteLLM CustomLogger that posts llm_call traces to the taOS trace API.

Registered as a LiteLLM callback so every chat completion routed through
the proxy is automatically captured in the per-agent trace store.

The callback extracts the agent slug from the LiteLLM key alias which the
deployer creates as ``taos-<slug>``. If no alias is found, the event is
recorded under the sentinel slug ``_unknown_`` so it's not silently
dropped.

Authentication uses the local token (``data/.auth_local_token``). The
path is resolved by probing the candidate locations described in
AuthManager.local_token_path(), with a final fallback to the
``TAOS_LOCAL_TOKEN`` env var injected by the deployer.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Sentinel used when no agent slug can be derived from the key alias.
_UNKNOWN_SLUG = "_unknown_"

# Candidate paths for the local auth token, searched in order.
_TOKEN_CANDIDATES = [
    Path("/data/.auth_local_token"),
    Path.home() / ".taos" / ".auth_local_token",
]


def _read_local_token() -> str:
    """Return the local auth token, trying candidate paths then env."""
    env_token = os.environ.get("TAOS_LOCAL_TOKEN", "")
    if env_token:
        return env_token
    for candidate in _TOKEN_CANDIDATES:
        try:
            if candidate.exists():
                return candidate.read_text().strip()
        except OSError:
            pass
    return ""


def _slug_from_alias(key_alias: str | None) -> str:
    """Extract agent slug from ``taos-<slug>`` key alias."""
    if key_alias and key_alias.startswith("taos-"):
        slug = key_alias[len("taos-"):]
        if slug:
            return slug
    return _UNKNOWN_SLUG


try:
    from litellm.integrations.custom_logger import CustomLogger as _CustomLogger

    class TaosLiteLLMCallback(_CustomLogger):
        """Posts llm_call + lifecycle/notify on every LiteLLM completion."""

        def __init__(self) -> None:
            super().__init__()
            self._trace_url: str = os.environ.get("TAOS_TRACE_URL", "http://127.0.0.1:6969/api/trace")
            self._notify_url: str = self._trace_url.replace("/api/trace", "/api/lifecycle/notify")

        async def _post(self, url: str, payload: dict) -> None:
            """Fire-and-forget POST; never raises into the caller."""
            try:
                import httpx
                token = _read_local_token()
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                async with httpx.AsyncClient(timeout=3) as client:
                    await client.post(url, json=payload, headers=headers)
            except Exception as exc:
                logger.warning("litellm_callback: POST to %s failed: %s", url, exc)

        def _extract_usage(self, response: Any) -> tuple[int, int, float]:
            """Return (tokens_in, tokens_out, cost_usd) from a LiteLLM response."""
            tokens_in = 0
            tokens_out = 0
            cost_usd = 0.0
            try:
                usage = getattr(response, "usage", None)
                if usage:
                    tokens_in = getattr(usage, "prompt_tokens", 0) or 0
                    tokens_out = getattr(usage, "completion_tokens", 0) or 0
                cost = getattr(response, "_hidden_params", {})
                if isinstance(cost, dict):
                    cost_usd = float(cost.get("response_cost", 0.0) or 0.0)
            except Exception:
                pass
            return tokens_in, tokens_out, cost_usd

        def _extract_messages(self, kwargs: dict) -> list:
            try:
                msgs = kwargs.get("messages") or []
                # Truncate large message lists to keep traces bounded.
                return [
                    {"role": m.get("role", ""), "content": str(m.get("content", ""))[:2000]}
                    for m in msgs[:50]
                ]
            except Exception:
                return []

        def _extract_response_text(self, response: Any) -> str:
            try:
                choices = getattr(response, "choices", [])
                if choices:
                    msg = getattr(choices[0], "message", None)
                    if msg:
                        return str(getattr(msg, "content", "") or "")
            except Exception:
                pass
            return ""

        def _extract_slug_and_model(self, kwargs: dict) -> tuple[str, str]:
            # LiteLLM puts the key alias in litellm_params or metadata
            litellm_params = kwargs.get("litellm_params") or {}
            metadata = litellm_params.get("metadata") or kwargs.get("metadata") or {}
            key_alias = metadata.get("key_alias") or litellm_params.get("key_alias")
            slug = _slug_from_alias(key_alias)
            model = str(kwargs.get("model") or "")
            return slug, model

        async def async_log_success_event(self, kwargs: dict, response_obj: Any, start_time: Any, end_time: Any) -> None:
            try:
                slug, model = self._extract_slug_and_model(kwargs)
                tokens_in, tokens_out, cost_usd = self._extract_usage(response_obj)
                duration_ms = 0
                try:
                    if start_time and end_time:
                        duration_ms = int((end_time - start_time).total_seconds() * 1000)
                except Exception:
                    pass
                backend_name = (kwargs.get("litellm_params") or {}).get("metadata", {}).get("backend_name") or ""
                payload = {
                    "status": "success",
                    "messages": self._extract_messages(kwargs),
                    "response": self._extract_response_text(response_obj),
                    "metadata": {
                        "model": model,
                        "backend_name": backend_name,
                    },
                }
                await self._post(self._trace_url, {
                    "agent_name": slug,
                    "kind": "llm_call",
                    "model": model,
                    "backend_name": backend_name or None,
                    "duration_ms": duration_ms,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost_usd": cost_usd,
                    "payload": payload,
                })
                if backend_name:
                    await self._post(self._notify_url, {"backend_name": backend_name})
            except Exception as exc:
                logger.warning("litellm_callback: success handler error: %s", exc)

        async def async_log_failure_event(self, kwargs: dict, response_obj: Any, start_time: Any, end_time: Any) -> None:
            try:
                slug, model = self._extract_slug_and_model(kwargs)
                duration_ms = 0
                try:
                    if start_time and end_time:
                        duration_ms = int((end_time - start_time).total_seconds() * 1000)
                except Exception:
                    pass
                backend_name = (kwargs.get("litellm_params") or {}).get("metadata", {}).get("backend_name") or ""
                error_msg = str(kwargs.get("exception") or response_obj or "unknown error")
                payload = {
                    "status": "failure",
                    "messages": self._extract_messages(kwargs),
                    "response": None,
                    "metadata": {
                        "model": model,
                        "backend_name": backend_name,
                        "error": error_msg,
                    },
                }
                await self._post(self._trace_url, {
                    "agent_name": slug,
                    "kind": "llm_call",
                    "model": model,
                    "backend_name": backend_name or None,
                    "duration_ms": duration_ms,
                    "error": error_msg,
                    "payload": payload,
                })
            except Exception as exc:
                logger.warning("litellm_callback: failure handler error: %s", exc)

    taos_callback = TaosLiteLLMCallback()

except ImportError:
    # LiteLLM not installed — define a no-op stub so the import never
    # fails. The proxy is optional; taOS works without it.
    logger.debug("litellm not installed — TaosLiteLLMCallback not registered")

    class _NoopCallback:  # type: ignore[no-redef]
        pass

    taos_callback = _NoopCallback()  # type: ignore[assignment]
