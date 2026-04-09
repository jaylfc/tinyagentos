"""Docker/Podman container backend using the docker CLI."""
from __future__ import annotations

import asyncio
import json
import logging

from .backend import ContainerBackend, ContainerInfo, _parse_memory

logger = logging.getLogger(__name__)


class DockerBackend(ContainerBackend):
    """Container backend that talks to docker or podman via CLI.

    Pass binary='podman' to use Podman instead of Docker.
    """

    def __init__(self, binary: str = "docker") -> None:
        self.binary = binary

    async def _run(self, cmd: list[str], timeout: int = 120) -> tuple[int, str]:
        """Run a command and return (returncode, output)."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode, stdout.decode() if stdout else ""

    async def list_containers(self, prefix: str = "agent-") -> list[ContainerInfo]:
        """List all containers whose name starts with prefix."""
        code, output = await self._run([
            self.binary, "ps", "-a",
            "--filter", f"name={prefix}",
            "--format", "{{json .}}",
        ])
        if code != 0:
            logger.error(f"{self.binary} ps failed: {output}")
            return []

        results = []
        for line in output.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            name = item.get("Names", item.get("Name", ""))
            # docker ps --format may return comma-separated names
            if isinstance(name, str):
                name = name.lstrip("/").split(",")[0].strip()

            if not name.startswith(prefix):
                continue

            state = item.get("State", item.get("Status", "unknown"))

            # Fetch IP via inspect
            ip = None
            icode, iout = await self._run([self.binary, "inspect", name])
            if icode == 0:
                try:
                    inspect = json.loads(iout)
                    if inspect:
                        networks = (
                            inspect[0]
                            .get("NetworkSettings", {})
                            .get("Networks", {})
                        )
                        for net in networks.values():
                            addr = net.get("IPAddress", "")
                            if addr:
                                ip = addr
                                break
                except (json.JSONDecodeError, IndexError, KeyError):
                    pass

            results.append(ContainerInfo(
                name=name,
                status=state,
                ip=ip,
                memory_mb=0,
                cpu_cores=0,
            ))
        return results

    async def create_container(
        self,
        name: str,
        image: str = "ubuntu:22.04",
        memory_limit: str = "2GB",
        cpu_limit: int = 2,
    ) -> dict:
        """Create and start a new container."""
        agent_name = name.removeprefix("agent-")
        code, output = await self._run([
            self.binary, "run", "-d",
            "--name", name,
            "--memory", memory_limit,
            "--cpus", str(cpu_limit),
            "-v", f"/data/agent-workspaces/{agent_name}:/workspace",
            "-v", f"/data/agent-memory/{agent_name}:/memory",
            image,
        ], timeout=300)
        if code != 0:
            return {"success": False, "error": output}
        return {"success": True, "name": name}

    async def exec_in_container(
        self, name: str, cmd: list[str], timeout: int = 300
    ) -> tuple[int, str]:
        """Execute a command inside a container."""
        return await self._run([self.binary, "exec", name] + cmd, timeout=timeout)

    async def push_file(
        self, name: str, local_path: str, remote_path: str
    ) -> tuple[int, str]:
        """Copy a file into a container."""
        return await self._run([self.binary, "cp", local_path, f"{name}:{remote_path}"])

    async def start_container(self, name: str) -> dict:
        code, output = await self._run([self.binary, "start", name])
        return {"success": code == 0, "output": output}

    async def stop_container(self, name: str) -> dict:
        code, output = await self._run([self.binary, "stop", name])
        return {"success": code == 0, "output": output}

    async def restart_container(self, name: str) -> dict:
        code, output = await self._run([self.binary, "restart", name])
        return {"success": code == 0, "output": output}

    async def destroy_container(self, name: str) -> dict:
        """Force-remove a container."""
        code, output = await self._run([self.binary, "rm", "-f", name])
        return {"success": code == 0, "output": output}

    async def get_container_logs(self, name: str, lines: int = 100) -> str:
        """Get recent log output from a container."""
        code, output = await self._run([
            self.binary, "logs", name, "--tail", str(lines),
        ])
        return output if code == 0 else f"Error getting logs: {output}"
