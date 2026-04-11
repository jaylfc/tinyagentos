import pytest
from tinyagentos.config import load_config
from tinyagentos.cluster.worker_protocol import WorkerInfo


@pytest.mark.asyncio
class TestAgentsPage:
    async def test_agents_page_returns_html(self, client):
        resp = await client.get("/agents")
        assert resp.status_code == 200
        assert "Agents" in resp.text

    async def test_list_agents_api(self, client):
        resp = await client.get("/api/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test-agent"

    async def test_add_agent(self, client, tmp_data_dir):
        resp = await client.post("/api/agents", json={
            "name": "new-agent", "host": "10.0.0.5", "qmd_index": "new", "color": "#ff0000",
        })
        assert resp.status_code == 200
        config = load_config(tmp_data_dir / "config.yaml")
        assert len(config.agents) == 2

    async def test_update_agent(self, client, tmp_data_dir):
        resp = await client.put("/api/agents/test-agent", json={"host": "10.0.0.99"})
        assert resp.status_code == 200
        config = load_config(tmp_data_dir / "config.yaml")
        assert config.agents[0]["host"] == "10.0.0.99"

    async def test_delete_agent(self, client, tmp_data_dir):
        resp = await client.delete("/api/agents/test-agent")
        assert resp.status_code == 200
        config = load_config(tmp_data_dir / "config.yaml")
        assert len(config.agents) == 0

    async def test_add_duplicate_agent_fails(self, client):
        resp = await client.post("/api/agents", json={
            "name": "test-agent", "host": "10.0.0.1", "qmd_index": "dup", "color": "#000",
        })
        assert resp.status_code == 409


@pytest.mark.asyncio
class TestBulkOperations:
    async def test_bulk_start(self, client):
        resp = await client.post("/api/agents/bulk/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "start"
        assert "results" in data
        # test-agent is in config
        assert "test-agent" in data["results"]

    async def test_bulk_stop(self, client):
        resp = await client.post("/api/agents/bulk/stop")
        assert resp.status_code == 200
        assert resp.json()["action"] == "stop"

    async def test_bulk_restart(self, client):
        resp = await client.post("/api/agents/bulk/restart")
        assert resp.status_code == 200
        assert resp.json()["action"] == "restart"


def _seed_worker(app, name, model_names, status="online"):
    """Add a fake worker with ``model_names`` loaded on one backend."""
    info = WorkerInfo(
        name=name,
        url=f"http://{name}.local:11434",
        hardware={},
        backends=[
            {
                "name": f"ollama@{name}",
                "type": "ollama",
                "url": f"http://{name}.local:11434",
                "capabilities": ["chat"],
                "models": [{"name": m, "size_mb": 0} for m in model_names],
                "status": "ok",
            }
        ],
        models=list(model_names),
        capabilities=["chat"],
        platform="linux",
        status=status,
    )
    app.state.cluster_manager._workers[name] = info
    return info


@pytest.mark.asyncio
class TestDeployRouting:
    """Cross-worker deploy routing (task #176 route-only stub)."""

    async def test_model_not_found_rejects_404(self, client, app):
        resp = await client.post("/api/agents/deploy", json={
            "name": "ghost-agent",
            "framework": "none",
            "model": "does-not-exist-anywhere",
        })
        assert resp.status_code == 404
        assert "not found" in resp.json()["error"].lower()

    async def test_worker_hosted_model_unpinned_routes_to_holder(self, client, app):
        _seed_worker(app, "fedora", ["qwen2.5-7b"])
        resp = await client.post("/api/agents/deploy", json={
            "name": "routed-agent",
            "framework": "none",
            "model": "qwen2.5-7b",
        })
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "routed"
        assert data["worker"] == "fedora"
        assert data["available_on"] == ["fedora"]
        # Must NOT have created a local agent entry
        config = app.state.config
        assert not any(a["name"] == "routed-agent" for a in config.agents)

    async def test_worker_hosted_model_pinned_to_holder_routes(self, client, app):
        _seed_worker(app, "fedora", ["qwen2.5-7b"])
        _seed_worker(app, "arch-box", ["phi3"])
        resp = await client.post("/api/agents/deploy", json={
            "name": "pinned-ok",
            "framework": "none",
            "model": "qwen2.5-7b",
            "target_worker": "fedora",
        })
        assert resp.status_code == 202
        data = resp.json()
        assert data["worker"] == "fedora"

    async def test_worker_hosted_model_pinned_to_wrong_worker_rejects_409(self, client, app):
        _seed_worker(app, "fedora", ["qwen2.5-7b"])
        _seed_worker(app, "arch-box", ["phi3"])
        resp = await client.post("/api/agents/deploy", json={
            "name": "pin-conflict",
            "framework": "none",
            "model": "qwen2.5-7b",
            "target_worker": "arch-box",
        })
        assert resp.status_code == 409
        data = resp.json()
        assert "not on worker" in data["error"]
        assert data["pinned_worker"] == "arch-box"
        assert data["available_on"] == ["fedora"]

    async def test_canonical_host_is_alphabetical_when_multiple_workers_have_model(
        self, client, app
    ):
        _seed_worker(app, "zeta", ["shared-model"])
        _seed_worker(app, "alpha", ["shared-model"])
        _seed_worker(app, "mid", ["shared-model"])
        resp = await client.post("/api/agents/deploy", json={
            "name": "multi-host",
            "framework": "none",
            "model": "shared-model",
        })
        assert resp.status_code == 202
        data = resp.json()
        assert data["worker"] == "alpha"
        assert data["available_on"] == ["alpha", "mid", "zeta"]

    async def test_controller_local_model_falls_through(self, client, app):
        # Stub the controller's live BackendCatalog to claim we have
        # "local-model" loaded. The deploy should NOT return 202/404 —
        # it should fall through to the existing controller-local path
        # (which then kicks off a background deploy).
        class _FakeCatalog:
            def all_models(self, capability=None):
                return [{"name": "local-model", "id": "local-model"}]

        app.state.backend_catalog = _FakeCatalog()

        # Make sure no worker is in the way.
        app.state.cluster_manager._workers.clear()

        resp = await client.post("/api/agents/deploy", json={
            "name": "local-agent",
            "framework": "none",
            "model": "local-model",
        })
        # Unchanged path returns the legacy 200 {"status": "deploying"}
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deploying"
        assert data["name"] == "local-agent"

    async def test_cloud_model_falls_through(self, client, app, tmp_data_dir):
        # Add a cloud provider with a model to the config and hit deploy.
        # Should fall through to the controller-local path, not 404.
        config = app.state.config
        config.backends.append({
            "name": "openai",
            "type": "openai",
            "url": "https://api.openai.com",
            "priority": 10,
            "models": [{"id": "gpt-4o-mini", "name": "GPT-4o mini"}],
        })
        # No workers, no local loaded catalog entry for this model.
        app.state.cluster_manager._workers.clear()

        resp = await client.post("/api/agents/deploy", json={
            "name": "cloud-agent",
            "framework": "none",
            "model": "gpt-4o-mini",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deploying"
