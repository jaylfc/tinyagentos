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

    async def test_delete_agent(self, client, tmp_data_dir, monkeypatch):
        async def fake_stop(name, force=False):
            return {"success": True, "output": ""}

        async def fake_rename(old, new):
            return {"success": True, "output": ""}

        monkeypatch.setattr("tinyagentos.containers.stop_container", fake_stop)
        monkeypatch.setattr("tinyagentos.containers.rename_container", fake_rename)
        resp = await client.delete("/api/agents/test-agent")
        assert resp.status_code == 200
        config = load_config(tmp_data_dir / "config.yaml")
        assert len(config.agents) == 0
        assert len(config.archived_agents) == 1

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


@pytest.mark.asyncio
class TestDeployPersistence:
    async def test_deploy_persists_model_and_framework(self, client, app, monkeypatch):
        """model + framework land on the agent row so later reads can see
        what the agent is actually configured for."""
        async def fake_deploy(req):
            return {"success": True, "name": req.name, "ip": "10.0.0.42",
                    "llm_key": "sk-test", "steps": ["deployment_complete"],
                    "container": f"taos-agent-{req.name}"}
        monkeypatch.setattr("tinyagentos.deployer.deploy_agent", fake_deploy)

        # Make "test-model" resolvable on the controller so the route doesn't 404
        class _FakeCatalog:
            def all_models(self, capability=None):
                return [{"name": "test-model", "id": "test-model"}]
        app.state.backend_catalog = _FakeCatalog()
        app.state.cluster_manager._workers.clear()

        resp = await client.post("/api/agents/deploy", json={
            "name": "persistent",
            "framework": "none",
            "model": "test-model",
            "color": "#abcdef",
        })
        assert resp.status_code == 200
        import asyncio
        await asyncio.sleep(0.2)

        detail = await client.get("/api/agents/persistent")
        assert detail.status_code == 200
        agent = detail.json()
        assert agent["model"] == "test-model"
        assert agent["framework"] == "none"
        assert agent["llm_key"] == "sk-test"
        assert agent["status"] == "running"
        assert agent["id"]  # uuid assigned

    async def test_deploy_creates_dm_channel(self, client, monkeypatch):
        async def fake_deploy(req):
            return {"success": True, "name": req.name, "ip": "10.0.0.43",
                    "llm_key": None, "steps": ["deployment_complete"],
                    "container": f"taos-agent-{req.name}"}
        monkeypatch.setattr("tinyagentos.deployer.deploy_agent", fake_deploy)

        resp = await client.post("/api/agents/deploy", json={
            "name": "chatter",
            "framework": "none",
            "color": "#112233",
        })
        assert resp.status_code == 200
        import asyncio
        await asyncio.sleep(0.2)

        detail = await client.get("/api/agents/chatter")
        agent = detail.json()
        channel_id = agent.get("chat_channel_id")
        assert channel_id, "deploy should create a DM channel and save its id"

        channels = await client.get("/api/chat/channels")
        assert channels.status_code == 200
        ch_list = channels.json().get("channels", [])
        assert any(c.get("id") == channel_id and c.get("type") == "dm" for c in ch_list)


@pytest.mark.asyncio
class TestAgentArchiveLifecycle:
    async def test_delete_archives_agent(self, client, monkeypatch):
        """DELETE /api/agents/{name} archives instead of destroying."""
        stopped = []
        renames = []

        async def fake_deploy(req):
            return {"success": True, "name": req.name, "ip": "10.0.0.44",
                    "llm_key": "sk-archive-test", "steps": ["deployment_complete"],
                    "container": f"taos-agent-{req.name}"}

        async def fake_stop(name, force=False):
            stopped.append(name)
            return {"success": True, "output": ""}

        async def fake_rename(old, new):
            renames.append((old, new))
            return {"success": True, "output": ""}

        monkeypatch.setattr("tinyagentos.deployer.deploy_agent", fake_deploy)
        monkeypatch.setattr("tinyagentos.containers.stop_container", fake_stop)
        monkeypatch.setattr("tinyagentos.containers.rename_container", fake_rename)

        await client.post("/api/agents/deploy", json={"name": "archiver", "framework": "none"})
        import asyncio
        await asyncio.sleep(0.2)

        resp = await client.delete("/api/agents/archiver")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "archived"
        assert data["name"] == "archiver"
        assert data["container"].startswith("taos-archived-archiver-")

        assert stopped == ["taos-agent-archiver"]
        assert len(renames) == 1
        assert renames[0][0] == "taos-agent-archiver"
        assert renames[0][1].startswith("taos-archived-archiver-")

        # Agent gone from live list
        live = (await client.get("/api/agents")).json()
        assert not any(a["name"] == "archiver" for a in live)

        # Agent present in archived list
        archived = (await client.get("/api/agents/archived")).json()
        assert any(a["original"]["name"] == "archiver" for a in archived)

    async def test_restore_archived_agent_with_new_slug_on_collision(self, client, app, monkeypatch):
        """Restoring when the original slug is taken by a new agent gets a
        suffixed slug; the archived entry is removed. Also verifies the
        env file is rewritten with the new LiteLLM key."""
        renames = []
        data_dir = app.state.data_dir

        async def fake_deploy(req):
            # Create the agent-home dir so the archive/restore cycle has
            # something to move, and so the env-file rewrite can fire.
            (req.data_dir / "agent-home" / req.name).mkdir(parents=True, exist_ok=True)
            return {"success": True, "name": req.name, "ip": "10.0.0.50",
                    "llm_key": "sk-x", "steps": [], "container": f"taos-agent-{req.name}"}

        async def fake_stop(name, force=False):
            return {"success": True, "output": ""}

        async def fake_rename(old, new):
            renames.append((old, new))
            return {"success": True, "output": ""}

        monkeypatch.setattr("tinyagentos.deployer.deploy_agent", fake_deploy)
        monkeypatch.setattr("tinyagentos.containers.stop_container", fake_stop)
        monkeypatch.setattr("tinyagentos.containers.rename_container", fake_rename)

        # Make llm_proxy appear running and return a fresh key on restore.
        proxy = app.state.llm_proxy
        monkeypatch.setattr(proxy, "is_running", lambda: True)
        async def fake_create_agent_key(name, models=None, budget_duration=None):
            return "sk-restored-key"
        monkeypatch.setattr(proxy, "create_agent_key", fake_create_agent_key)

        await client.post("/api/agents/deploy", json={"name": "rest", "framework": "none"})
        import asyncio
        await asyncio.sleep(0.2)
        await client.delete("/api/agents/rest")
        # Deploy a new agent that takes the slug
        await client.post("/api/agents/deploy", json={"name": "rest", "framework": "none"})
        await asyncio.sleep(0.2)

        archived = (await client.get("/api/agents/archived")).json()
        assert len(archived) == 1
        archive_id = archived[0]["id"]

        resp = await client.post(f"/api/agents/archived/{archive_id}/restore")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "restored"
        assert data["name"] == "rest-2"

        # Archive list now empty
        archived2 = (await client.get("/api/agents/archived")).json()
        assert archived2 == []

        # Two live agents named rest + rest-2
        live = {a["name"] for a in (await client.get("/api/agents")).json()}
        assert {"rest", "rest-2"} <= live

        # The restore path writes the new key to the agent's env file so
        # the container reads a fresh credential on next start.
        from tinyagentos.agent_env import read_env_file
        home_dir = data_dir / "agent-home" / data["name"]
        env = read_env_file(home_dir)
        assert env.get("OPENAI_API_KEY") == "sk-restored-key"

    async def test_archive_moves_home_dir_too(self, client, app, monkeypatch):
        """Archive sweeps workspace, memory, AND the new home dir into
        the archive bucket."""
        data_dir = app.state.data_dir

        async def fake_deploy(req):
            (req.data_dir / "agent-workspaces" / req.name).mkdir(parents=True, exist_ok=True)
            (req.data_dir / "agent-memory" / req.name).mkdir(parents=True, exist_ok=True)
            (req.data_dir / "agent-home" / req.name).mkdir(parents=True, exist_ok=True)
            (req.data_dir / "agent-workspaces" / req.name / "w.txt").write_text("w")
            (req.data_dir / "agent-memory" / req.name / "m.txt").write_text("m")
            (req.data_dir / "agent-home" / req.name / "h.txt").write_text("h")
            return {"success": True, "name": req.name, "ip": "10.0.0.81",
                    "llm_key": None, "steps": [], "container": f"taos-agent-{req.name}"}

        async def fake_stop(name, force=False): return {"success": True, "output": ""}
        async def fake_rename(old, new): return {"success": True, "output": ""}

        monkeypatch.setattr("tinyagentos.deployer.deploy_agent", fake_deploy)
        monkeypatch.setattr("tinyagentos.containers.stop_container", fake_stop)
        monkeypatch.setattr("tinyagentos.containers.rename_container", fake_rename)

        await client.post("/api/agents/deploy", json={"name": "triad", "framework": "none"})
        import asyncio
        await asyncio.sleep(0.2)
        resp = await client.delete("/api/agents/triad")
        assert resp.status_code == 200

        archived = (await client.get("/api/agents/archived")).json()
        assert len(archived) == 1
        archive_dir_rel = archived[0]["archive_dir"]

        from pathlib import Path
        archive_base = data_dir / archive_dir_rel
        assert (archive_base / "workspace" / "w.txt").read_text() == "w"
        assert (archive_base / "memory" / "m.txt").read_text() == "m"
        assert (archive_base / "home" / "h.txt").read_text() == "h"

    async def test_archive_aborts_when_rename_fails(self, client, app, monkeypatch):
        """If rename fails for a container that exists, config must NOT
        move to archived_agents — the user needs to fix state and retry."""
        async def fake_deploy(req):
            return {"success": True, "name": req.name, "ip": "10.0.0.82",
                    "llm_key": None, "steps": [], "container": f"taos-agent-{req.name}"}

        async def fake_stop(name, force=False): return {"success": True, "output": ""}

        async def fake_rename(old, new):
            return {"success": False, "output": "Error: Instance is still running"}

        monkeypatch.setattr("tinyagentos.deployer.deploy_agent", fake_deploy)
        monkeypatch.setattr("tinyagentos.containers.stop_container", fake_stop)
        monkeypatch.setattr("tinyagentos.containers.rename_container", fake_rename)

        await client.post("/api/agents/deploy", json={"name": "stuck", "framework": "none"})
        import asyncio
        await asyncio.sleep(0.2)

        resp = await client.delete("/api/agents/stuck")
        assert resp.status_code == 500
        assert "could not rename" in resp.json()["error"]

        # Still in live list, not in archived
        live = (await client.get("/api/agents")).json()
        assert any(a["name"] == "stuck" for a in live)
        archived = (await client.get("/api/agents/archived")).json()
        assert not any(a.get("archived_slug") == "stuck" for a in archived)

    async def test_purge_archived_destroys_for_real(self, client, monkeypatch, tmp_path):
        """DELETE /api/agents/archived/{id} destroys container + archive dir."""
        destroyed = []

        async def fake_deploy(req):
            return {"success": True, "name": req.name, "ip": "10.0.0.60",
                    "llm_key": None, "steps": [], "container": f"taos-agent-{req.name}"}

        async def fake_stop(name, force=False):
            return {"success": True, "output": ""}

        async def fake_rename(old, new):
            return {"success": True, "output": ""}

        async def fake_destroy(name):
            destroyed.append(name)
            return {"success": True, "output": ""}

        monkeypatch.setattr("tinyagentos.deployer.deploy_agent", fake_deploy)
        monkeypatch.setattr("tinyagentos.containers.stop_container", fake_stop)
        monkeypatch.setattr("tinyagentos.containers.rename_container", fake_rename)
        monkeypatch.setattr("tinyagentos.containers.destroy_container", fake_destroy)

        await client.post("/api/agents/deploy", json={"name": "purgeable", "framework": "none"})
        import asyncio
        await asyncio.sleep(0.2)
        await client.delete("/api/agents/purgeable")

        archived = (await client.get("/api/agents/archived")).json()
        archive_id = archived[0]["id"]

        resp = await client.delete(f"/api/agents/archived/{archive_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "purged"
        assert any(n.startswith("taos-archived-purgeable-") for n in destroyed)

        archived2 = (await client.get("/api/agents/archived")).json()
        assert archived2 == []


@pytest.mark.asyncio
class TestArchivedChatPersistence:
    """Archive preserves chat messages; restore re-imports; purge deletes all."""

    async def _setup_agent_with_channel(self, client, monkeypatch, slug="chat-agent"):
        """Deploy an agent, create its DM channel, send messages, archive it."""
        async def fake_deploy(req):
            return {"success": True, "name": req.name, "ip": "10.0.0.70",
                    "llm_key": None, "steps": [], "container": f"taos-agent-{req.name}"}

        async def fake_stop(name, force=False):
            return {"success": True, "output": ""}

        async def fake_rename(old, new):
            return {"success": True, "output": ""}

        monkeypatch.setattr("tinyagentos.deployer.deploy_agent", fake_deploy)
        monkeypatch.setattr("tinyagentos.containers.stop_container", fake_stop)
        monkeypatch.setattr("tinyagentos.containers.rename_container", fake_rename)

        deploy_resp = await client.post("/api/agents/deploy", json={"name": slug, "framework": "none"})
        assert deploy_resp.status_code == 200
        import asyncio
        await asyncio.sleep(0.2)

        app = client._transport.app
        ch_store = app.state.chat_channels
        msg_store = app.state.chat_messages

        # Create DM channel and wire it to the agent config.
        ch = await ch_store.create_channel(
            name=f"dm-{slug}", type="dm", created_by="user",
            members=[slug, "user"],
        )
        # Inject chat_channel_id into agent config so _archive_agent_fully finds it.
        config = app.state.config
        for a in config.agents:
            if a["name"] == slug:
                a["chat_channel_id"] = ch["id"]
                break
        from tinyagentos.config import save_config_locked
        await save_config_locked(config, config.config_path)

        # Send a couple of messages.
        m1 = await msg_store.send_message(ch["id"], slug, "agent", "hello from agent")
        m2 = await msg_store.send_message(ch["id"], "user", "user", "hi agent")

        return ch, [m1, m2]

    async def test_archive_writes_chat_export(self, client, monkeypatch, tmp_data_dir):
        """Archive writes chat-export.jsonl into agent-home/.taos/."""
        ch, msgs = await self._setup_agent_with_channel(client, monkeypatch)

        async def fake_stop(name, force=False):
            return {"success": True, "output": ""}

        async def fake_rename(old, new):
            return {"success": True, "output": ""}

        monkeypatch.setattr("tinyagentos.containers.stop_container", fake_stop)
        monkeypatch.setattr("tinyagentos.containers.rename_container", fake_rename)

        # Create agent-home dir so export can be written.
        agent_home = tmp_data_dir / "agent-home" / "chat-agent"
        agent_home.mkdir(parents=True, exist_ok=True)

        resp = await client.delete("/api/agents/chat-agent")
        assert resp.status_code == 200

        # Find the archive directory.
        app = client._transport.app
        config = app.state.config
        entry = config.archived_agents[-1]
        archive_base = tmp_data_dir / entry["archive_dir"]

        export_path = archive_base / "home" / ".taos" / "chat-export.jsonl"
        assert export_path.exists(), f"chat-export.jsonl missing at {export_path}"

        import json
        lines = [json.loads(l) for l in export_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 2
        contents = {l["content"] for l in lines}
        assert "hello from agent" in contents
        assert "hi agent" in contents

        # Channel should be flagged archived with full metadata.
        ch_store = app.state.chat_channels
        updated_ch = await ch_store.get_channel(ch["id"])
        s = updated_ch["settings"]
        assert s.get("archived") is True
        assert "archived_at" in s
        assert s.get("archived_agent_id") == entry["id"]
        assert s.get("archived_agent_slug") == "chat-agent"

    async def test_restore_reimports_messages_and_unflags_channel(
        self, client, monkeypatch, tmp_data_dir
    ):
        """Restore: missing messages come back, channel is unflagged."""
        ch, msgs = await self._setup_agent_with_channel(client, monkeypatch, slug="restore-agent")

        async def fake_stop(name, force=False):
            return {"success": True, "output": ""}

        async def fake_rename(old, new):
            return {"success": True, "output": ""}

        monkeypatch.setattr("tinyagentos.containers.stop_container", fake_stop)
        monkeypatch.setattr("tinyagentos.containers.rename_container", fake_rename)

        # Create agent-home dir so export can be written.
        (tmp_data_dir / "agent-home" / "restore-agent").mkdir(parents=True, exist_ok=True)

        await client.delete("/api/agents/restore-agent")

        app = client._transport.app
        config = app.state.config
        entry = config.archived_agents[-1]
        archive_id = entry["id"]

        # Simulate messages deleted from DB (to verify re-import).
        msg_store = app.state.chat_messages
        for m in msgs:
            await msg_store.delete_message(m["id"])
        remaining = await msg_store.get_messages(ch["id"], limit=100)
        assert len(remaining) == 0

        # Restore.
        resp = await client.post(f"/api/agents/archived/{archive_id}/restore")
        assert resp.status_code == 200

        # Messages re-imported.
        reimported = await msg_store.get_messages(ch["id"], limit=100)
        assert len(reimported) == 2
        contents = {m["content"] for m in reimported}
        assert "hello from agent" in contents

        # Channel unflagged.
        ch_store = app.state.chat_channels
        updated_ch = await ch_store.get_channel(ch["id"])
        assert updated_ch["settings"].get("archived") is False

    async def test_restore_is_idempotent(self, client, monkeypatch, tmp_data_dir):
        """Re-importing the same messages twice does not create duplicates."""
        ch, msgs = await self._setup_agent_with_channel(client, monkeypatch, slug="idem-agent")

        async def fake_stop(name, force=False):
            return {"success": True, "output": ""}

        async def fake_rename(old, new):
            return {"success": True, "output": ""}

        monkeypatch.setattr("tinyagentos.containers.stop_container", fake_stop)
        monkeypatch.setattr("tinyagentos.containers.rename_container", fake_rename)

        (tmp_data_dir / "agent-home" / "idem-agent").mkdir(parents=True, exist_ok=True)
        await client.delete("/api/agents/idem-agent")

        app = client._transport.app
        config = app.state.config
        entry = config.archived_agents[-1]
        archive_id = entry["id"]
        export_path = (tmp_data_dir / entry["archive_dir"]) / "home" / ".taos" / "chat-export.jsonl"
        assert export_path.exists()

        # Call ensure_message directly on the same data twice.
        import json
        msg_store = app.state.chat_messages
        lines = [json.loads(l) for l in export_path.read_text().splitlines() if l.strip()]
        for _ in range(2):
            for line in lines:
                await msg_store.ensure_message(line)

        # Still exactly the original count (2).
        all_msgs = await msg_store.get_messages(ch["id"], limit=100)
        assert len(all_msgs) == 2

    async def test_purge_deletes_channel_and_messages(
        self, client, monkeypatch, tmp_data_dir
    ):
        """Purge removes messages, channel, and archive dir."""
        ch, msgs = await self._setup_agent_with_channel(client, monkeypatch, slug="purge-agent")

        async def fake_stop(name, force=False):
            return {"success": True, "output": ""}

        async def fake_rename(old, new):
            return {"success": True, "output": ""}

        async def fake_destroy(name):
            return {"success": True, "output": ""}

        monkeypatch.setattr("tinyagentos.containers.stop_container", fake_stop)
        monkeypatch.setattr("tinyagentos.containers.rename_container", fake_rename)
        monkeypatch.setattr("tinyagentos.containers.destroy_container", fake_destroy)

        (tmp_data_dir / "agent-home" / "purge-agent").mkdir(parents=True, exist_ok=True)
        await client.delete("/api/agents/purge-agent")

        app = client._transport.app
        config = app.state.config
        entry = config.archived_agents[-1]
        archive_id = entry["id"]

        resp = await client.delete(f"/api/agents/archived/{archive_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "purged"

        # Channel gone.
        ch_store = app.state.chat_channels
        assert await ch_store.get_channel(ch["id"]) is None

        # Messages gone.
        msg_store = app.state.chat_messages
        remaining = await msg_store.get_messages(ch["id"], limit=100)
        assert len(remaining) == 0

        # Archive dir gone.
        archive_base = tmp_data_dir / entry["archive_dir"]
        assert not archive_base.exists()
