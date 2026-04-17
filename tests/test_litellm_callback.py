"""Tests for tinyagentos.litellm_callback."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(tokens_in=10, tokens_out=20, content="hello"):
    resp = MagicMock()
    resp.usage = MagicMock(prompt_tokens=tokens_in, completion_tokens=tokens_out)
    resp._hidden_params = {"response_cost": 0.001}
    choice = MagicMock()
    choice.message = MagicMock(content=content)
    resp.choices = [choice]
    return resp


def _make_kwargs(model="default", key_alias="taos-my-agent", messages=None, backend_name="local"):
    return {
        "model": model,
        "messages": messages or [{"role": "user", "content": "hi"}],
        "litellm_params": {
            "metadata": {
                "key_alias": key_alias,
                "backend_name": backend_name,
            }
        },
    }


# ---------------------------------------------------------------------------
# _slug_from_alias
# ---------------------------------------------------------------------------

def test_slug_from_alias_happy_path():
    from tinyagentos.litellm_callback import _slug_from_alias
    assert _slug_from_alias("taos-my-agent") == "my-agent"


def test_slug_from_alias_no_prefix():
    from tinyagentos.litellm_callback import _slug_from_alias, _UNKNOWN_SLUG
    assert _slug_from_alias("some-other-key") == _UNKNOWN_SLUG


def test_slug_from_alias_none():
    from tinyagentos.litellm_callback import _slug_from_alias, _UNKNOWN_SLUG
    assert _slug_from_alias(None) == _UNKNOWN_SLUG


def test_slug_from_alias_bare_taos_prefix():
    from tinyagentos.litellm_callback import _slug_from_alias, _UNKNOWN_SLUG
    assert _slug_from_alias("taos-") == _UNKNOWN_SLUG


# ---------------------------------------------------------------------------
# _read_local_token
# ---------------------------------------------------------------------------

def test_read_local_token_from_env(monkeypatch):
    monkeypatch.setenv("TAOS_LOCAL_TOKEN", "tok-abc")
    from importlib import reload
    import tinyagentos.litellm_callback as mod
    reload(mod)
    assert mod._read_local_token() == "tok-abc"
    monkeypatch.delenv("TAOS_LOCAL_TOKEN", raising=False)


def test_read_local_token_from_file(tmp_path, monkeypatch):
    monkeypatch.delenv("TAOS_LOCAL_TOKEN", raising=False)
    token_file = tmp_path / ".auth_local_token"
    token_file.write_text("file-token-123")
    import tinyagentos.litellm_callback as mod
    original = mod._TOKEN_CANDIDATES
    mod._TOKEN_CANDIDATES = [token_file]
    try:
        assert mod._read_local_token() == "file-token-123"
    finally:
        mod._TOKEN_CANDIDATES = original


# ---------------------------------------------------------------------------
# TaosLiteLLMCallback — success event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_log_success_posts_trace():
    try:
        from tinyagentos.litellm_callback import TaosLiteLLMCallback
    except ImportError:
        pytest.skip("litellm not installed")

    cb = TaosLiteLLMCallback()
    posted = []

    async def _mock_post(url, payload):
        posted.append((url, payload))

    cb._post = _mock_post

    from datetime import datetime, timezone
    t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2024, 1, 1, 10, 0, 1, tzinfo=timezone.utc)
    resp = _make_response(tokens_in=5, tokens_out=10, content="world")
    kwargs = _make_kwargs(key_alias="taos-agent-x", backend_name="ollama-local")

    await cb.async_log_success_event(kwargs, resp, t0, t1)

    # Should have posted trace and lifecycle notify
    assert len(posted) == 2
    trace_url, trace_payload = posted[0]
    assert trace_payload["agent_name"] == "agent-x"
    assert trace_payload["kind"] == "llm_call"
    assert trace_payload["tokens_in"] == 5
    assert trace_payload["tokens_out"] == 10
    assert trace_payload["payload"]["status"] == "success"

    notify_url, notify_payload = posted[1]
    assert notify_payload["backend_name"] == "ollama-local"


@pytest.mark.asyncio
async def test_async_log_failure_posts_trace():
    try:
        from tinyagentos.litellm_callback import TaosLiteLLMCallback
    except ImportError:
        pytest.skip("litellm not installed")

    cb = TaosLiteLLMCallback()
    posted = []

    async def _mock_post(url, payload):
        posted.append((url, payload))

    cb._post = _mock_post

    from datetime import datetime, timezone
    t0 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2024, 1, 1, 10, 0, 2, tzinfo=timezone.utc)
    kwargs = _make_kwargs(key_alias="taos-agent-y", backend_name="")
    kwargs["exception"] = "Connection refused"

    await cb.async_log_failure_event(kwargs, None, t0, t1)

    assert len(posted) == 1
    _, payload = posted[0]
    assert payload["kind"] == "llm_call"
    assert payload["agent_name"] == "agent-y"
    assert payload["payload"]["status"] == "failure"
    assert "Connection refused" in (payload.get("error") or "")


@pytest.mark.asyncio
async def test_callback_never_raises_on_bad_input():
    try:
        from tinyagentos.litellm_callback import TaosLiteLLMCallback
    except ImportError:
        pytest.skip("litellm not installed")

    cb = TaosLiteLLMCallback()

    async def _raise_post(url, payload):
        raise RuntimeError("network gone")

    cb._post = _raise_post

    # Should not raise even when _post fails
    await cb.async_log_success_event({}, None, None, None)
    await cb.async_log_failure_event({}, None, None, None)


# ---------------------------------------------------------------------------
# taos_callback module-level instance
# ---------------------------------------------------------------------------

def test_taos_callback_importable():
    from tinyagentos.litellm_callback import taos_callback
    assert taos_callback is not None
