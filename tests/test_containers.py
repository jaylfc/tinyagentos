import json
import pytest
from unittest.mock import AsyncMock, patch
from tinyagentos.containers import (
    list_containers, create_container, start_container,
    stop_container, destroy_container, _parse_memory, ContainerInfo,
)


class TestParseMemory:
    def test_gb(self):
        assert _parse_memory("2GB") == 2048

    def test_mb(self):
        assert _parse_memory("512MB") == 512

    def test_zero(self):
        assert _parse_memory("0") == 0

    def test_empty(self):
        assert _parse_memory("") == 0


class TestListContainers:
    @pytest.mark.asyncio
    async def test_parses_incus_output(self):
        mock_output = json.dumps([
            {
                "name": "agent-naira",
                "status": "Running",
                "config": {"limits.memory": "2GB", "limits.cpu": "2"},
                "state": {
                    "network": {
                        "eth0": {
                            "addresses": [
                                {"family": "inet", "address": "10.0.0.5", "scope": "global"}
                            ]
                        }
                    }
                }
            },
            {
                "name": "not-an-agent",
                "status": "Running",
                "config": {},
                "state": {"network": {}},
            }
        ])
        with patch("tinyagentos.containers._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, mock_output)
            containers = await list_containers()
            assert len(containers) == 1
            assert containers[0].name == "agent-naira"
            assert containers[0].status == "Running"
            assert containers[0].ip == "10.0.0.5"
            assert containers[0].memory_mb == 2048

    @pytest.mark.asyncio
    async def test_handles_incus_failure(self):
        with patch("tinyagentos.containers._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (1, "error")
            containers = await list_containers()
            assert containers == []


class TestCreateContainer:
    @pytest.mark.asyncio
    async def test_creates_and_configures(self):
        with patch("tinyagentos.containers._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "")
            result = await create_container("agent-test", memory_limit="1GB", cpu_limit=1)
            assert result["success"] is True
            # Should have called: launch, set memory, set cpu
            assert mock_run.call_count == 3

    @pytest.mark.asyncio
    async def test_handles_launch_failure(self):
        with patch("tinyagentos.containers._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (1, "launch failed")
            result = await create_container("agent-test")
            assert result["success"] is False


class TestContainerLifecycle:
    @pytest.mark.asyncio
    async def test_start(self):
        with patch("tinyagentos.containers._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "")
            result = await start_container("agent-test")
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_stop(self):
        with patch("tinyagentos.containers._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "")
            result = await stop_container("agent-test")
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_destroy(self):
        with patch("tinyagentos.containers._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "")
            result = await destroy_container("agent-test")
            assert result["success"] is True
            # Should have called stop --force then delete --force
            assert mock_run.call_count == 2
