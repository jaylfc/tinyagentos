import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tinyagentos.deployer import deploy_agent, undeploy_agent, DeployRequest


class TestDeployAgent:
    @pytest.mark.asyncio
    async def test_full_deployment_flow(self):
        req = DeployRequest(
            name="test",
            framework="smolagents",
            model=None,
            rkllama_url="http://localhost:8080",
        )

        call_count = 0

        async def mock_exec(name, cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            cmd_str = " ".join(cmd)
            if "hostname -I" in cmd_str:
                return (0, "10.0.0.5")
            return (0, "ok")

        with patch("tinyagentos.deployer.create_container", new_callable=AsyncMock) as mock_create, \
             patch("tinyagentos.deployer.exec_in_container", side_effect=mock_exec), \
             patch("tinyagentos.deployer.push_file", new_callable=AsyncMock) as mock_push:
            mock_create.return_value = {"success": True, "name": "agent-test"}
            mock_push.return_value = (0, "")

            result = await deploy_agent(req)
            assert result["success"] is True
            assert result["name"] == "test"
            assert result["container"] == "agent-test"
            assert result["ip"] == "10.0.0.5"
            assert "deployment_complete" in result["steps"]

    @pytest.mark.asyncio
    async def test_handles_container_creation_failure(self):
        req = DeployRequest(name="fail", framework="smolagents", model=None)
        with patch("tinyagentos.deployer.create_container", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = {"success": False, "error": "no space"}
            result = await deploy_agent(req)
            assert result["success"] is False
            assert "no space" in result["error"]


    @pytest.mark.asyncio
    async def test_deployment_with_llm_proxy(self):
        """Test that deployer injects proxy env vars when proxy is running."""
        mock_proxy = MagicMock()
        mock_proxy.is_running.return_value = True
        mock_proxy.url = "http://localhost:4000"
        mock_proxy.create_agent_key = AsyncMock(return_value="sk-test-key-123")

        req = DeployRequest(
            name="proxy-test",
            framework="smolagents",
            model=None,
            extra_config={"llm_proxy": mock_proxy},
        )

        async def mock_exec_fn(name, cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "hostname -I" in cmd_str:
                return (0, "10.0.0.6")
            return (0, "ok")

        with patch("tinyagentos.deployer.create_container", new_callable=AsyncMock) as mock_create, \
             patch("tinyagentos.deployer.exec_in_container", side_effect=mock_exec_fn), \
             patch("tinyagentos.deployer.push_file", new_callable=AsyncMock) as mock_push:
            mock_create.return_value = {"success": True, "name": "agent-proxy-test"}
            mock_push.return_value = (0, "")

            result = await deploy_agent(req)
            assert result["success"] is True
            assert result["llm_key"] == "sk-test-key-123"
            assert "llm_proxy_key_injected" in result["steps"]
            mock_proxy.create_agent_key.assert_called_once_with("proxy-test")

    @pytest.mark.asyncio
    async def test_deployment_without_llm_proxy(self):
        """Test that deployment works normally without proxy."""
        req = DeployRequest(
            name="no-proxy",
            framework="smolagents",
            model=None,
        )

        async def mock_exec_fn(name, cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "hostname -I" in cmd_str:
                return (0, "10.0.0.7")
            return (0, "ok")

        with patch("tinyagentos.deployer.create_container", new_callable=AsyncMock) as mock_create, \
             patch("tinyagentos.deployer.exec_in_container", side_effect=mock_exec_fn), \
             patch("tinyagentos.deployer.push_file", new_callable=AsyncMock) as mock_push:
            mock_create.return_value = {"success": True, "name": "agent-no-proxy"}
            mock_push.return_value = (0, "")

            result = await deploy_agent(req)
            assert result["success"] is True
            assert result.get("llm_key") is None


class TestBackgroundDeploy:
    @pytest.mark.asyncio
    async def test_deploy_endpoint_returns_immediately(self, client):
        """POST /api/agents/deploy should return immediately with status=deploying."""
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
        """GET /api/agents/{name}/deploy-status returns task state."""
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
            mock_destroy.assert_called_once_with("agent-test")
