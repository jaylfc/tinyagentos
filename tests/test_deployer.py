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
