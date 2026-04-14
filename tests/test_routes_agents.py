import pytest
from tinyagentos.config import load_config
from tinyagentos.cluster.worker_protocol import WorkerInfo


@pytest.mark.asyncio
class TestAgentsPage:
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

    async def test_add_duplicate_name_gets_suffixed(self, client):
        """POSTing with an already-taken name succeeds; the slug is auto-suffixed.

        The UI-facing display_name is preserved verbatim, so the user sees
        both copies by their original name — the suffix is only on the
        internal slug used for paths, containers, and URLs.
        """
        resp = await client.post("/api/agents", json={
            "name": "test-agent", "host": "10.0.0.1", "qmd_index": "dup", "color": "#000",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "created"
        assert data["display_name"] == "test-agent"
        assert data["name"] == "test-agent-2"


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


@pytest.mark.asyncio
class TestResumeRoute:
    async def test_resume_clears_paused_flag(self, client, app, tmp_data_dir):
        # Manually pause the test-agent
        agent = app.state.config.agents[0]
        assert agent["name"] == "test-agent"
        agent["paused"] = True

        resp = await client.post("/api/agents/test-agent/resume")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "resumed"
        assert data["paused"] is False

        # Persisted to disk too
        from tinyagentos.config import load_config
        config = load_config(tmp_data_dir / "config.yaml")
        assert config.agents[0].get("paused") is False

    async def test_resume_not_found(self, client):
        resp = await client.post("/api/agents/no-such-agent/resume")
        assert resp.status_code == 404

    async def test_resume_already_running(self, client):
        """Resuming a non-paused agent is a no-op, returns 200."""
        resp = await client.post("/api/agents/test-agent/resume")
        assert resp.status_code == 200
        data = resp.json()
        assert data["paused"] is False


@pytest.mark.asyncio
class TestModelUpdateRoute:
    async def test_model_update_with_reachable_model(self, client, app):
        """Updating to a model that lives on an online worker succeeds."""
        _seed_worker(app, "gpu-box", ["qwen2.5-7b"])

        resp = await client.post("/api/agents/test-agent/model", json={"model": "qwen2.5-7b"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "updated"
        assert data["model"] == "qwen2.5-7b"

    async def test_model_update_resumes_paused_agent(self, client, app, tmp_data_dir):
        """Swapping model on a paused agent clears the paused flag."""
        _seed_worker(app, "gpu-box", ["phi3"])
        agent = app.state.config.agents[0]
        agent["paused"] = True

        resp = await client.post("/api/agents/test-agent/model", json={"model": "phi3"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["resumed"] is True
        assert data["paused"] is False if "paused" in data else True

        from tinyagentos.config import load_config
        config = load_config(tmp_data_dir / "config.yaml")
        assert config.agents[0].get("paused") is False

    async def test_model_update_rejects_unreachable_model(self, client, app):
        """Requesting a model that no worker has returns 409."""
        app.state.cluster_manager._workers.clear()

        resp = await client.post("/api/agents/test-agent/model", json={"model": "ghost-model"})
        assert resp.status_code == 409
        data = resp.json()
        assert "not reachable" in data["error"]

    async def test_model_update_not_found(self, client):
        resp = await client.post("/api/agents/no-such-agent/model", json={"model": "phi3"})
        assert resp.status_code == 404

    async def test_model_update_empty_model_rejected(self, client):
        resp = await client.post("/api/agents/test-agent/model", json={"model": "   "})
        assert resp.status_code == 400

    async def test_model_update_with_local_model(self, client, app):
        """A model in the local backend catalog is reachable."""
        class _FakeCatalog:
            def all_models(self, capability=None):
                return [{"name": "local-llm", "id": "local-llm"}]

        app.state.backend_catalog = _FakeCatalog()
        app.state.cluster_manager._workers.clear()

        resp = await client.post("/api/agents/test-agent/model", json={"model": "local-llm"})
        assert resp.status_code == 200
