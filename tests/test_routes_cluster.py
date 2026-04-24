"""Tests for the cluster API routes."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_worker_registration_api(client):
    body = {
        "name": "test-worker",
        "url": "http://192.168.1.50:9000",
        "platform": "linux",
        "capabilities": ["chat", "embed"],
        "hardware": {"cpu": "Ryzen 9", "ram_gb": 64},
        "models": ["llama3"],
    }
    resp = await client.post("/api/cluster/workers", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "registered"
    assert data["name"] == "test-worker"

    # Verify it shows up in the list
    resp = await client.get("/api/cluster/workers")
    assert resp.status_code == 200
    workers = resp.json()
    assert len(workers) == 1
    assert workers[0]["name"] == "test-worker"
    assert workers[0]["status"] == "online"


@pytest.mark.asyncio
async def test_heartbeat_api(client):
    # Register first
    await client.post("/api/cluster/workers", json={
        "name": "hb-worker", "url": "http://10.0.0.1:9000", "capabilities": ["chat"],
    })

    # Send heartbeat
    resp = await client.post("/api/cluster/heartbeat", json={
        "name": "hb-worker", "load": 0.42, "models": ["phi3"],
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify updated values
    resp = await client.get("/api/cluster/workers")
    w = resp.json()[0]
    assert w["load"] == 0.42
    assert w["models"] == ["phi3"]


@pytest.mark.asyncio
async def test_heartbeat_unknown_worker(client):
    resp = await client.post("/api/cluster/heartbeat", json={"name": "ghost"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unregister_worker(client):
    await client.post("/api/cluster/workers", json={
        "name": "temp-worker", "url": "http://10.0.0.2:9000",
    })
    resp = await client.delete("/api/cluster/workers/temp-worker")
    assert resp.status_code == 200
    assert resp.json()["status"] == "removed"

    # Verify gone
    resp = await client.get("/api/cluster/workers")
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_unregister_unknown_worker(client):
    resp = await client.delete("/api/cluster/workers/ghost")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_capabilities_api(client):
    await client.post("/api/cluster/workers", json={
        "name": "w1", "url": "http://10.0.0.1:9000", "capabilities": ["chat", "embed"],
    })
    await client.post("/api/cluster/workers", json={
        "name": "w2", "url": "http://10.0.0.2:9000", "capabilities": ["chat", "tts"],
    })

    resp = await client.get("/api/cluster/capabilities")
    assert resp.status_code == 200
    caps = resp.json()
    assert "chat" in caps
    assert sorted(caps["chat"]) == ["w1", "w2"]
    assert caps["embed"] == ["w1"]
    assert caps["tts"] == ["w2"]


@pytest.mark.asyncio
async def test_worker_registration_includes_kv_quant(client):
    body = {
        "name": "quant-worker",
        "url": "http://10.0.0.9:9000",
        "kv_cache_quant_support": ["fp16", "turboquant-k3v2"],
    }
    resp = await client.post("/api/cluster/workers", json=body)
    assert resp.status_code == 200

    resp = await client.get("/api/cluster/workers")
    workers = resp.json()
    assert len(workers) == 1
    assert workers[0]["kv_cache_quant_support"] == ["fp16", "turboquant-k3v2"]


@pytest.mark.asyncio
async def test_worker_registration_kv_quant_defaults_fp16(client):
    """A worker that doesn't send kv_cache_quant_support gets ["fp16"] by default."""
    body = {
        "name": "legacy-worker",
        "url": "http://10.0.0.8:9000",
        # no kv_cache_quant_support field
    }
    resp = await client.post("/api/cluster/workers", json=body)
    assert resp.status_code == 200

    resp = await client.get("/api/cluster/workers")
    workers = resp.json()
    assert workers[0]["kv_cache_quant_support"] == ["fp16"]


@pytest.mark.asyncio
async def test_heartbeat_updates_kv_quant(client):
    await client.post("/api/cluster/workers", json={
        "name": "kv-worker",
        "url": "http://10.0.0.7:9000",
        "kv_cache_quant_support": ["fp16"],
    })

    resp = await client.post("/api/cluster/heartbeat", json={
        "name": "kv-worker",
        "load": 0.1,
        "kv_cache_quant_support": ["fp16", "turboquant-k3v2"],
    })
    assert resp.status_code == 200

    resp = await client.get("/api/cluster/workers")
    w = resp.json()[0]
    assert "turboquant-k3v2" in w["kv_cache_quant_support"]


@pytest.mark.asyncio
async def test_kv_quant_options_empty_cluster(client):
    resp = await client.get("/api/cluster/kv-quant-options")
    assert resp.status_code == 200
    data = resp.json()
    assert "options" in data
    assert data["options"] == ["fp16"]


@pytest.mark.asyncio
async def test_kv_quant_options_all_fp16(client):
    for i in range(2):
        await client.post("/api/cluster/workers", json={
            "name": f"w{i}",
            "url": f"http://10.0.1.{i}:9000",
            "kv_cache_quant_support": ["fp16"],
        })
    resp = await client.get("/api/cluster/kv-quant-options")
    data = resp.json()
    assert data["options"] == ["fp16"]


@pytest.mark.asyncio
async def test_kv_quant_options_mixed_cluster(client):
    await client.post("/api/cluster/workers", json={
        "name": "plain",
        "url": "http://10.0.2.1:9000",
        "kv_cache_quant_support": ["fp16"],
    })
    await client.post("/api/cluster/workers", json={
        "name": "turboquant",
        "url": "http://10.0.2.2:9000",
        "kv_cache_quant_support": ["fp16", "turboquant-k3v2"],
    })
    resp = await client.get("/api/cluster/kv-quant-options")
    data = resp.json()
    assert "fp16" in data["options"]
    assert "turboquant-k3v2" in data["options"]


# ---------------------------------------------------------------------------
# incus-enroll endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_incus_enroll_worker_not_registered(client):
    """404 when the worker has never registered."""
    resp = await client.post(
        "/api/cluster/workers/ghost-worker/incus-enroll",
        json={"incus_url": "https://10.0.0.5:8443", "token": "abc123"},
    )
    assert resp.status_code == 404
    assert "not registered" in resp.json()["error"]


@pytest.mark.asyncio
async def test_incus_enroll_success(client):
    """Happy path: worker registered → remote_add called with right args → 200."""
    await client.post("/api/cluster/workers", json={
        "name": "pi-worker",
        "url": "http://10.0.0.5:9000",
    })

    mock_remote_add = AsyncMock(return_value={"success": True, "output": ""})
    with patch("tinyagentos.containers.remote_add", mock_remote_add):
        resp = await client.post(
            "/api/cluster/workers/pi-worker/incus-enroll",
            json={"incus_url": "https://10.0.0.5:8443", "token": "tok-xyz"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    mock_remote_add.assert_awaited_once_with(
        "pi-worker", "https://10.0.0.5:8443", "tok-xyz"
    )


@pytest.mark.asyncio
async def test_incus_enroll_remote_add_failure(client):
    """remote_add returns failure → endpoint returns 500 with error text."""
    await client.post("/api/cluster/workers", json={
        "name": "flaky-worker",
        "url": "http://10.0.0.6:9000",
    })

    mock_remote_add = AsyncMock(return_value={
        "success": False,
        "output": "certificate rejected",
    })
    with patch("tinyagentos.containers.remote_add", mock_remote_add):
        resp = await client.post(
            "/api/cluster/workers/flaky-worker/incus-enroll",
            json={"incus_url": "https://10.0.0.6:8443", "token": "bad-tok"},
        )

    assert resp.status_code == 500
    data = resp.json()
    assert data["ok"] is False
    assert "certificate rejected" in data["error"]
