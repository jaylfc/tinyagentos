import json
import pytest
from unittest.mock import AsyncMock, patch
from tinyagentos.containers import (
    list_containers, create_container, set_root_quota,
    start_container, stop_container, destroy_container,
    _parse_memory, ContainerInfo,
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
                "name": "taos-agent-naira",
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
            assert containers[0].name == "taos-agent-naira"
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
            result = await create_container("taos-agent-test", memory_limit="1GB", cpu_limit=1)
            assert result["success"] is True
            # Should have called: launch, set memory, set cpu
            assert mock_run.call_count == 3

    @pytest.mark.asyncio
    async def test_handles_launch_failure(self):
        with patch("tinyagentos.containers._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (1, "launch failed")
            result = await create_container("taos-agent-test")
            assert result["success"] is False


class TestSetRootQuota:
    @pytest.mark.asyncio
    async def test_success(self):
        with patch("tinyagentos.containers._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "")
            result = await set_root_quota("taos-agent-test", 40)
            assert result["success"] is True
            assert "40" in result["note"]
            cmd = mock_run.call_args[0][0]
            assert "incus" in cmd
            assert "config" in cmd
            assert "device" in cmd
            assert "set" in cmd
            assert "root" in cmd
            assert "size=40GiB" in cmd

    @pytest.mark.asyncio
    async def test_failure_returns_success_false(self):
        with patch("tinyagentos.containers._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (1, "device not found")
            result = await set_root_quota("taos-agent-test", 40)
            assert result["success"] is False
            assert "device not found" in result["note"]

    @pytest.mark.asyncio
    async def test_create_container_passes_root_size_gib(self):
        """root_size_gib passed to create_container triggers set_root_quota."""
        calls = []
        async def mock_run(cmd, timeout=120):
            calls.append(cmd)
            return (0, "")

        with patch("tinyagentos.containers._run", side_effect=mock_run):
            result = await create_container("taos-agent-test", root_size_gib=40)
        assert result["success"] is True
        # At least one call should set the root size
        quota_calls = [c for c in calls if "size=40GiB" in " ".join(c)]
        assert quota_calls, "expected a quota set call with size=40GiB"


class TestContainerLifecycle:
    @pytest.mark.asyncio
    async def test_start(self):
        with patch("tinyagentos.containers._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "")
            result = await start_container("taos-agent-test")
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_stop(self):
        with patch("tinyagentos.containers._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "")
            result = await stop_container("taos-agent-test")
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_destroy(self):
        with patch("tinyagentos.containers._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "")
            result = await destroy_container("taos-agent-test")
            assert result["success"] is True
            # Should have called stop --force then delete --force
            assert mock_run.call_count == 2
