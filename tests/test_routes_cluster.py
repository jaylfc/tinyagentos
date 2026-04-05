"""Tests for the cluster API routes."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_cluster_page_renders(client):
    resp = await client.get("/cluster")
    assert resp.status_code == 200
    assert "Compute Cluster" in resp.text


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
async def test_cluster_page_shows_workers(client):
    await client.post("/api/cluster/workers", json={
        "name": "dashboard-worker", "url": "http://10.0.0.5:9000",
        "capabilities": ["chat"], "platform": "linux",
    })
    resp = await client.get("/cluster")
    assert resp.status_code == 200
    assert "dashboard-worker" in resp.text
