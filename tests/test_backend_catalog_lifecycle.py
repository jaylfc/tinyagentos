from __future__ import annotations
import asyncio
import pytest
from tinyagentos.scheduler.backend_catalog import BackendCatalog, BackendEntry


@pytest.mark.asyncio
async def test_disabled_backend_excluded_from_routing():
    """A backend with enabled=False must not appear in backends_with_capability."""
    async def probe(backend: dict) -> dict:
        return {"status": "ok", "response_ms": 1, "models": []}

    backends = [
        {"name": "b1", "type": "rkllama", "url": "http://b1", "priority": 1, "enabled": False},
        {"name": "b2", "type": "rkllama", "url": "http://b2", "priority": 2, "enabled": True},
    ]
    catalog = BackendCatalog(backends=backends, probe_fn=probe, interval_seconds=3600)
    await catalog.start()
    try:
        results = catalog.backends_with_capability("llm-chat")
        assert len(results) == 1
        assert results[0].name == "b2"
    finally:
        await catalog.stop()


@pytest.mark.asyncio
async def test_lifecycle_state_in_to_dict():
    """BackendEntry.to_dict() must include lifecycle fields."""
    async def probe(backend: dict) -> dict:
        return {"status": "ok", "response_ms": 5, "models": []}

    backends = [
        {
            "name": "b1", "type": "rkllama", "url": "http://b1", "priority": 1,
            "enabled": True, "auto_manage": True, "keep_alive_minutes": 10,
        }
    ]
    catalog = BackendCatalog(backends=backends, probe_fn=probe, interval_seconds=3600)
    await catalog.start()
    try:
        entries = catalog.backends()
        assert len(entries) == 1
        d = entries[0].to_dict()
        assert d["lifecycle_state"] == "running"
        assert d["auto_manage"] is True
        assert d["keep_alive_minutes"] == 10
        assert d["enabled"] is True
    finally:
        await catalog.stop()


@pytest.mark.asyncio
async def test_stopped_backend_in_backends_startable():
    """A stopped+auto_manage backend appears in backends_startable_for_capability."""
    async def probe(backend: dict) -> dict:
        return {"status": "error", "response_ms": 0, "models": []}

    backends = [
        {
            "name": "b1", "type": "rknn-sd", "url": "http://b1", "priority": 1,
            "enabled": True, "auto_manage": True, "keep_alive_minutes": 10,
        }
    ]
    catalog = BackendCatalog(backends=backends, probe_fn=probe, interval_seconds=3600)
    catalog._lifecycle_states["b1"] = "stopped"
    await catalog.start()
    try:
        startable = catalog.backends_startable_for_capability("image-generation")
        assert len(startable) == 1
        assert startable[0].name == "b1"
    finally:
        await catalog.stop()


@pytest.mark.asyncio
async def test_set_and_get_lifecycle_state():
    """set_lifecycle_state and get_lifecycle_state round-trip correctly."""
    async def probe(backend: dict) -> dict:
        return {"status": "ok", "response_ms": 1, "models": []}

    backends = [{"name": "b1", "type": "rkllama", "url": "http://b1", "priority": 1}]
    catalog = BackendCatalog(backends=backends, probe_fn=probe, interval_seconds=3600)
    await catalog.start()
    try:
        assert catalog.get_lifecycle_state("b1") == "running"
        catalog.set_lifecycle_state("b1", "stopped")
        assert catalog.get_lifecycle_state("b1") == "stopped"
    finally:
        await catalog.stop()
