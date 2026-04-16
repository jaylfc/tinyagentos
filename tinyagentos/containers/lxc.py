"""LXC container backend using the incus CLI."""
from __future__ import annotations

import asyncio
import json
import logging

from .backend import ContainerBackend, ContainerInfo, _parse_memory

logger = logging.getLogger(__name__)


async def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    """Run a command and return (returncode, output)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return proc.returncode, stdout.decode() if stdout else ""


class LXCBackend(ContainerBackend):
    """Container backend that talks to incus via CLI."""

    async def _run(self, cmd: list[str], timeout: int = 120) -> tuple[int, str]:
        return await _run(cmd, timeout=timeout)

    async def list_containers(self, prefix: str = "taos-agent-") -> list[ContainerInfo]:
        """List all agent containers."""
        code, output = await _run(["incus", "list", "-f", "json"])
        if code != 0:
            logger.error(f"incus list failed: {output}")
            return []
        try:
            containers = json.loads(output)
        except json.JSONDecodeError:
            return []
        results = []
        for c in containers:
            name = c.get("name", "")
            if not name.startswith(prefix):
                continue
            status = c.get("status", "Unknown")
            ip = None
            network = c.get("state", {}).get("network", {})
            for iface in network.values():
                for addr in iface.get("addresses", []):
                    if addr.get("family") == "inet" and addr.get("scope") == "global":
                        ip = addr.get("address")
                        break
                if ip:
                    break
            config = c.get("config", {})
            mem_str = config.get("limits.memory", "0")
            memory_mb = _parse_memory(mem_str)
            cpu_str = config.get("limits.cpu", "0")
            cpu_cores = int(cpu_str) if cpu_str.isdigit() else 0
            results.append(ContainerInfo(
                name=name, status=status, ip=ip,
                memory_mb=memory_mb, cpu_cores=cpu_cores,
            ))
        return results

    async def create_container(
        self,
        name: str,
        image: str = "images:debian/bookworm",
        memory_limit: str | None = None,
        cpu_limit: int | None = None,
        mounts: list[tuple[str, str]] | None = None,
        env: dict[str, str] | None = None,
    ) -> dict:
        """Create and start a new LXC container.

        Bind mounts are attached as disk devices via ``incus config device
        add`` and env vars via ``incus config set environment.KEY VALUE``.
        The container image itself holds only the framework and base OS;
        every piece of per-agent state enters through one of the mounts
        or reaches a host service named by one of the env vars. See
        ``docs/design/framework-agnostic-runtime.md``.
        """
        code, output = await _run(
            ["incus", "launch", image, name], timeout=300,
        )
        if code != 0:
            return {"success": False, "error": output}

        if memory_limit is not None:
            await _run(["incus", "config", "set", name, "limits.memory", memory_limit])
        if cpu_limit is not None:
            await _run(["incus", "config", "set", name, "limits.cpu", str(cpu_limit)])

        for idx, (host_path, container_path) in enumerate(mounts or []):
            device_name = f"taos-mount-{idx}"
            mcode, mout = await _run([
                "incus", "config", "device", "add", name, device_name, "disk",
                f"source={host_path}", f"path={container_path}",
            ])
            if mcode != 0:
                logger.error(f"incus mount {host_path}->{container_path} failed: {mout}")

        for key, value in (env or {}).items():
            ecode, eout = await _run([
                "incus", "config", "set", name, f"environment.{key}", value,
            ])
            if ecode != 0:
                logger.error(f"incus env set {key} failed: {eout}")

        return {"success": True, "name": name}

    async def exec_in_container(
        self, name: str, cmd: list[str], timeout: int = 300
    ) -> tuple[int, str]:
        """Execute a command inside a container."""
        return await _run(["incus", "exec", name, "--"] + cmd, timeout=timeout)

    async def push_file(
        self, name: str, local_path: str, remote_path: str
    ) -> tuple[int, str]:
        """Push a file into a container."""
        return await _run(["incus", "file", "push", local_path, f"{name}{remote_path}"])

    async def start_container(self, name: str) -> dict:
        code, output = await _run(["incus", "start", name])
        return {"success": code == 0, "output": output}

    async def stop_container(self, name: str) -> dict:
        code, output = await _run(["incus", "stop", name])
        return {"success": code == 0, "output": output}

    async def restart_container(self, name: str) -> dict:
        code, output = await _run(["incus", "restart", name])
        return {"success": code == 0, "output": output}

    async def destroy_container(self, name: str) -> dict:
        """Stop and delete a container."""
        await _run(["incus", "stop", name, "--force"])
        code, output = await _run(["incus", "delete", name, "--force"])
        return {"success": code == 0, "output": output}

    async def get_container_logs(self, name: str, lines: int = 100) -> str:
        """Get recent logs from a container's journal."""
        code, output = await self.exec_in_container(
            name, ["journalctl", "--no-pager", "-n", str(lines)], timeout=30,
        )
        return output if code == 0 else f"Error getting logs: {output}"

    async def rename_container(self, old_name: str, new_name: str) -> dict:
        code, output = await _run(["incus", "rename", old_name, new_name])
        return {"success": code == 0, "output": output}
