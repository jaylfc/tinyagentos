import json
import pytest
from unittest.mock import AsyncMock, patch, call
from tinyagentos.containers import (
    list_containers, create_container, set_root_quota, set_env,
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
    async def test_success_via_override(self):
        """set_root_quota uses incus config device override (not set) as primary path."""
        with patch("tinyagentos.containers._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "")
            result = await set_root_quota("taos-agent-test", 40)
            assert result["success"] is True
            assert "40" in result["note"]
            cmd = mock_run.call_args[0][0]
            assert "incus" in cmd
            assert "config" in cmd
            assert "device" in cmd
            assert "override" in cmd
            assert "root" in cmd
            assert "size=40GiB" in cmd

    @pytest.mark.asyncio
    async def test_fallback_to_set_when_override_already_exists(self):
        """Falls back to device set when override reports 'already exists'."""
        calls = []
        async def mock_run(cmd, timeout=120):
            calls.append(cmd)
            if "override" in cmd:
                return (1, "Device already exists")
            return (0, "")

        with patch("tinyagentos.containers._run", side_effect=mock_run):
            result = await set_root_quota("taos-agent-test", 40)
        assert result["success"] is True
        # First call must be override, second must be set
        assert "override" in calls[0]
        assert "set" in calls[1]

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
        # At least one call should set the root size via override
        quota_calls = [c for c in calls if "size=40GiB" in " ".join(c)]
        assert quota_calls, "expected a quota set call with size=40GiB"
        override_calls = [c for c in calls if "override" in c]
        assert override_calls, "expected an override call for profile-inherited root device"


class TestSetEnv:
    @pytest.mark.asyncio
    async def test_env_uses_key_equals_value_form(self):
        """incus env set uses key=value single-arg form (not separate positional value)."""
        with patch("tinyagentos.containers._run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "")
            result = await set_env("taos-agent-test", "MY_KEY", "myvalue")
            assert result["success"] is True
            cmd = mock_run.call_args[0][0]
            # The key=value must appear as one element, not split across two
            assert "environment.MY_KEY=myvalue" in cmd
            # The value must NOT appear as a separate trailing argument
            assert cmd[-1] == "environment.MY_KEY=myvalue"

    @pytest.mark.asyncio
    async def test_env_dash_prefixed_value_no_flag_error(self):
        """A token value starting with '-' must not be parsed as a CLI flag.

        Regression for: incus env set TAOS_LOCAL_TOKEN failed:
        Error: unknown shorthand flag: 'X' in -XOvCacuHM1H...
        """
        dash_token = "-Xabc123secrettoken"
        calls = []
        async def mock_run(cmd, timeout=120):
            calls.append(cmd)
            # Simulate incus succeeding (no flag parse error)
            return (0, "")

        with patch("tinyagentos.containers._run", side_effect=mock_run):
            result = await set_env("taos-agent-test", "TAOS_LOCAL_TOKEN", dash_token)
        assert result["success"] is True
        assert len(calls) == 1
        cmd = calls[0]
        # Value embedded in key=value arg — never a standalone arg that could be a flag
        assert f"environment.TAOS_LOCAL_TOKEN={dash_token}" in cmd
        # Confirm the token is NOT a separate final element
        assert cmd[-1] != dash_token

    @pytest.mark.asyncio
    async def test_create_container_env_uses_key_equals_value_form(self):
        """create_container env loop also uses key=value form."""
        calls = []
        async def mock_run(cmd, timeout=120):
            calls.append(cmd)
            return (0, "")

        with patch("tinyagentos.containers._run", side_effect=mock_run):
            result = await create_container(
                "taos-agent-test",
                env={"TAOS_LOCAL_TOKEN": "-Xsecret", "OTHER": "val"},
            )
        assert result["success"] is True
        env_calls = [c for c in calls if any("environment." in e for e in c)]
        assert len(env_calls) == 2
        for c in env_calls:
            # Each env arg must be a single key=value element
            env_args = [e for e in c if e.startswith("environment.")]
            assert len(env_args) == 1
            assert "=" in env_args[0]


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
