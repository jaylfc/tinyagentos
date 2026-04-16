from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tinyagentos.deployer import deploy_agent, undeploy_agent, DeployRequest


def _req(**overrides) -> DeployRequest:
    defaults = dict(
        name="test",
        framework="smolagents",
        model=None,
        data_dir=Path("/tmp/taos-test-data"),
    )
    defaults.update(overrides)
    return DeployRequest(**defaults)


class TestDeployAgent:
    @pytest.mark.asyncio
    async def test_full_deployment_flow(self, tmp_path):
        req = _req(data_dir=tmp_path)

        async def mock_exec(name, cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "hostname -I" in cmd_str:
                return (0, "10.0.0.5")
            return (0, "ok")

        with patch("tinyagentos.deployer.create_container", new_callable=AsyncMock) as mock_create, \
             patch("tinyagentos.deployer.exec_in_container", side_effect=mock_exec):
            mock_create.return_value = {"success": True, "name": "taos-agent-test"}

            result = await deploy_agent(req)
            assert result["success"] is True
            assert result["name"] == "test"
            assert result["container"] == "taos-agent-test"
            assert result["ip"] == "10.0.0.5"
            assert "deployment_complete" in result["steps"]

            # Mounts and env are passed to create_container — the
            # framework-agnostic runtime rule in action.
            call_kwargs = mock_create.call_args.kwargs
            mounts = call_kwargs["mounts"]
            assert (str(tmp_path / "agent-workspaces" / "test"), "/workspace") in mounts
            assert (str(tmp_path / "agent-memory" / "test"), "/memory") in mounts
            env = call_kwargs["env"]
            assert env["TAOS_AGENT_NAME"] == "test"
            assert env["TAOS_SKILLS_URL"].endswith("/api/skill-exec")

    @pytest.mark.asyncio
    async def test_handles_container_creation_failure(self, tmp_path):
        req = _req(name="fail", data_dir=tmp_path)
        with patch("tinyagentos.deployer.create_container", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {"success": False, "error": "no space"}
            result = await deploy_agent(req)
            assert result["success"] is False
            assert "no space" in result["error"]

    @pytest.mark.asyncio
    async def test_deployment_with_llm_proxy_injects_embedding_url(self, tmp_path):
        """LLM proxy wired → OPENAI_BASE_URL and TAOS_EMBEDDING_URL land in env."""
        mock_proxy = MagicMock()
        mock_proxy.is_running.return_value = True
        mock_proxy.url = "http://localhost:4000"
        mock_proxy.create_agent_key = AsyncMock(return_value="sk-test-key-123")

        req = _req(
            name="proxy-test",
            data_dir=tmp_path,
            extra_config={"llm_proxy": mock_proxy},
        )

        async def mock_exec_fn(name, cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "hostname -I" in cmd_str:
                return (0, "10.0.0.6")
            return (0, "ok")

        with patch("tinyagentos.deployer.create_container", new_callable=AsyncMock) as mock_create, \
             patch("tinyagentos.deployer.exec_in_container", side_effect=mock_exec_fn):
            mock_create.return_value = {"success": True, "name": "taos-agent-proxy-test"}

            result = await deploy_agent(req)
            assert result["success"] is True
            assert result["llm_key"] == "sk-test-key-123"
            env = mock_create.call_args.kwargs["env"]
            assert env["OPENAI_API_KEY"] == "sk-test-key-123"
            assert env["OPENAI_BASE_URL"] == "http://localhost:4000/v1"
            assert env["TAOS_EMBEDDING_URL"] == "http://localhost:4000/v1/embeddings"
            mock_proxy.create_agent_key.assert_called_once_with("proxy-test")

    @pytest.mark.asyncio
    async def test_deployment_without_llm_proxy(self, tmp_path):
        req = _req(name="no-proxy", data_dir=tmp_path)

        async def mock_exec_fn(name, cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "hostname -I" in cmd_str:
                return (0, "10.0.0.7")
            return (0, "ok")

        with patch("tinyagentos.deployer.create_container", new_callable=AsyncMock) as mock_create, \
             patch("tinyagentos.deployer.exec_in_container", side_effect=mock_exec_fn):
            mock_create.return_value = {"success": True, "name": "taos-agent-no-proxy"}

            result = await deploy_agent(req)
            assert result["success"] is True
            assert result.get("llm_key") is None
            env = mock_create.call_args.kwargs["env"]
            assert "OPENAI_API_KEY" not in env
            assert "TAOS_EMBEDDING_URL" not in env

    @pytest.mark.asyncio
    async def test_model_name_injected_into_env(self, tmp_path):
        """Selected model lands in TAOS_MODEL so the in-container runtime
        can pass it through to LiteLLM."""
        req = _req(name="with-model", model="claude-3.5-sonnet", data_dir=tmp_path)

        async def mock_exec_fn(name, cmd, **kwargs):
            if "hostname -I" in " ".join(cmd):
                return (0, "10.0.0.8")
            return (0, "ok")

        with patch("tinyagentos.deployer.create_container", new_callable=AsyncMock) as mock_create, \
             patch("tinyagentos.deployer.exec_in_container", side_effect=mock_exec_fn):
            mock_create.return_value = {"success": True, "name": "taos-agent-with-model"}
            result = await deploy_agent(req)
            assert result["success"] is True
            env = mock_create.call_args.kwargs["env"]
            assert env["TAOS_MODEL"] == "claude-3.5-sonnet"

    @pytest.mark.asyncio
    async def test_base_deps_include_npm_and_build_essentials(self, tmp_path):
        """Agent containers need node/npm/build-essential for frameworks
        with native modules. Make sure the dep install command has them."""
        req = _req(name="deps", data_dir=tmp_path)
        recorded = []

        async def mock_exec_fn(name, cmd, **kwargs):
            cmd_str = " ".join(cmd)
            recorded.append(cmd_str)
            if "hostname -I" in cmd_str:
                return (0, "10.0.0.9")
            return (0, "ok")

        with patch("tinyagentos.deployer.create_container", new_callable=AsyncMock) as mock_create, \
             patch("tinyagentos.deployer.exec_in_container", side_effect=mock_exec_fn):
            mock_create.return_value = {"success": True, "name": "taos-agent-deps"}
            await deploy_agent(req)

        apt_commands = [c for c in recorded if "apt-get install" in c]
        assert apt_commands, "expected an apt-get install command"
        apt = apt_commands[0]
        for pkg in ("nodejs", "npm", "build-essential", "ca-certificates", "python3"):
            assert pkg in apt, f"{pkg} missing from apt install: {apt}"

    @pytest.mark.asyncio
    async def test_framework_install_failure_rolls_back(self, tmp_path):
        """Framework install failing must mark the deploy as failed so the
        UI doesn't mislead users with status=running on a broken agent."""
        req = _req(name="brokenfw", framework="nonexistent-pkg", data_dir=tmp_path)

        async def mock_exec_fn(name, cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "hostname -I" in cmd_str:
                return (0, "10.0.0.10")
            if "pip3 install nonexistent-pkg" in cmd_str:
                return (1, "ERROR: No matching distribution found")
            return (0, "ok")

        with patch("tinyagentos.deployer.create_container", new_callable=AsyncMock) as mock_create, \
             patch("tinyagentos.deployer.exec_in_container", side_effect=mock_exec_fn), \
             patch("tinyagentos.deployer.destroy_container", new_callable=AsyncMock) as mock_destroy:
            mock_create.return_value = {"success": True, "name": "taos-agent-brokenfw"}
            mock_destroy.return_value = {"success": True}
            result = await deploy_agent(req)
            assert result["success"] is False
            assert "Framework install failed" in result["error"]
            mock_destroy.assert_called_once()

    @pytest.mark.asyncio
    async def test_manifest_pip_install(self, tmp_path):
        """When the framework manifest declares method: pip, use the
        declared package name (which may differ from the framework id)."""
        mock_manifest = MagicMock()
        mock_manifest.install = {"method": "pip", "package": "smolagents"}
        mock_manifest.manifest_dir = tmp_path
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_manifest

        req = _req(
            name="pip-install", framework="smolagents", data_dir=tmp_path,
            extra_config={"registry": mock_registry},
        )

        recorded = []
        async def mock_exec_fn(name, cmd, **kwargs):
            recorded.append(" ".join(cmd))
            if "hostname -I" in " ".join(cmd):
                return (0, "10.0.0.11")
            return (0, "ok")

        with patch("tinyagentos.deployer.create_container", new_callable=AsyncMock) as mock_create, \
             patch("tinyagentos.deployer.exec_in_container", side_effect=mock_exec_fn):
            mock_create.return_value = {"success": True, "name": "taos-agent-pip-install"}
            result = await deploy_agent(req)
            assert result["success"] is True
            assert any("pip3 install smolagents" in c for c in recorded)
            mock_registry.get.assert_called_once_with("smolagents")

    @pytest.mark.asyncio
    async def test_manifest_script_install(self, tmp_path):
        """method: script pushes the script into the container and runs it."""
        script_dir = tmp_path / "openclaw"
        script_dir.mkdir()
        script_path = script_dir / "install.sh"
        script_path.write_text("#!/bin/bash\necho installing\n")

        mock_manifest = MagicMock()
        mock_manifest.install = {"method": "script", "script": "install.sh"}
        mock_manifest.manifest_dir = script_dir
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_manifest

        req = _req(
            name="scripted", framework="openclaw", data_dir=tmp_path,
            extra_config={"registry": mock_registry},
        )

        recorded_execs = []
        async def mock_exec_fn(name, cmd, **kwargs):
            recorded_execs.append(" ".join(cmd))
            if "hostname -I" in " ".join(cmd):
                return (0, "10.0.0.12")
            return (0, "ok")

        with patch("tinyagentos.deployer.create_container", new_callable=AsyncMock) as mock_create, \
             patch("tinyagentos.deployer.exec_in_container", side_effect=mock_exec_fn), \
             patch("tinyagentos.deployer.push_file", new_callable=AsyncMock) as mock_push:
            mock_create.return_value = {"success": True, "name": "taos-agent-scripted"}
            mock_push.return_value = (0, "")
            result = await deploy_agent(req)
            assert result["success"] is True
            mock_push.assert_called_once()
            # verify the script was executed in the container
            assert any("bash /tmp/install.sh" in c for c in recorded_execs)

    @pytest.mark.asyncio
    async def test_manifest_script_missing_file_fails(self, tmp_path):
        mock_manifest = MagicMock()
        mock_manifest.install = {"method": "script", "script": "install.sh"}
        mock_manifest.manifest_dir = tmp_path  # script NOT written here
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_manifest

        req = _req(
            name="missingscript", framework="openclaw", data_dir=tmp_path,
            extra_config={"registry": mock_registry},
        )

        async def mock_exec_fn(name, cmd, **kwargs):
            if "hostname -I" in " ".join(cmd):
                return (0, "10.0.0.13")
            return (0, "ok")

        with patch("tinyagentos.deployer.create_container", new_callable=AsyncMock) as mock_create, \
             patch("tinyagentos.deployer.exec_in_container", side_effect=mock_exec_fn), \
             patch("tinyagentos.deployer.destroy_container", new_callable=AsyncMock) as mock_destroy:
            mock_create.return_value = {"success": True, "name": "taos-agent-missingscript"}
            mock_destroy.return_value = {"success": True}
            result = await deploy_agent(req)
            assert result["success"] is False
            assert "Install script missing" in result["error"]


class TestBackgroundDeploy:
    @pytest.mark.asyncio
    async def test_deploy_endpoint_returns_immediately(self, client):
        resp = await client.post("/api/agents/deploy", json={
            "name": "bg-test",
            "framework": "none",
            "color": "#aabbcc",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deploying"
        assert data["name"] == "bg-test"

    @pytest.mark.asyncio
    async def test_deploy_status_endpoint(self, client):
        await client.post("/api/agents/deploy", json={
            "name": "status-test",
            "framework": "none",
        })
        resp = await client.get("/api/agents/status-test/deploy-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("deploying", "success", "failed")

    @pytest.mark.asyncio
    async def test_deploy_status_not_found(self, client):
        resp = await client.get("/api/agents/nonexistent/deploy-status")
        assert resp.status_code == 404


class TestUndeployAgent:
    @pytest.mark.asyncio
    async def test_undeploy(self):
        with patch("tinyagentos.deployer.destroy_container", new_callable=AsyncMock) as mock_destroy:
            mock_destroy.return_value = {"success": True, "output": ""}
            result = await undeploy_agent("test")
            assert result["success"] is True
            mock_destroy.assert_called_once_with("taos-agent-test")


class TestUndeployWithStateCleanup:
    @pytest.mark.asyncio
    async def test_undeploy_delete_state_wipes_dirs(self, tmp_path):
        # Pre-create the dirs the way deploy_agent would
        (tmp_path / "agent-workspaces" / "wiper").mkdir(parents=True)
        (tmp_path / "agent-memory" / "wiper").mkdir(parents=True)
        (tmp_path / "agent-workspaces" / "wiper" / "marker.txt").write_text("x")

        with patch("tinyagentos.deployer.destroy_container", new_callable=AsyncMock) as mock_destroy:
            mock_destroy.return_value = {"success": True, "output": ""}
            result = await undeploy_agent("wiper", data_dir=tmp_path, delete_state=True)
            assert result["success"] is True
            assert not (tmp_path / "agent-workspaces" / "wiper").exists()
            assert not (tmp_path / "agent-memory" / "wiper").exists()

    @pytest.mark.asyncio
    async def test_undeploy_without_delete_state_keeps_dirs(self, tmp_path):
        (tmp_path / "agent-workspaces" / "keeper").mkdir(parents=True)
        with patch("tinyagentos.deployer.destroy_container", new_callable=AsyncMock) as mock_destroy:
            mock_destroy.return_value = {"success": True, "output": ""}
            result = await undeploy_agent("keeper", data_dir=tmp_path, delete_state=False)
            assert result["success"] is True
            assert (tmp_path / "agent-workspaces" / "keeper").exists()
