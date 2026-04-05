"""LXC container management via incus CLI."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

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


@dataclass
class ContainerInfo:
    name: str
    status: str  # Running | Stopped | ...
    ip: str | None
    memory_mb: int
    cpu_cores: int


async def list_containers(prefix: str = "agent-") -> list[ContainerInfo]:
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
        # Parse memory limit from config
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


def _parse_memory(mem_str: str) -> int:
    """Parse memory string like '2GB' or '512MB' to megabytes."""
    mem_str = mem_str.strip().upper()
    if not mem_str or mem_str == "0":
        return 0
    if mem_str.endswith("GB"):
        return int(float(mem_str[:-2]) * 1024)
    if mem_str.endswith("MB"):
        return int(float(mem_str[:-2]))
    if mem_str.endswith("KB"):
        return int(float(mem_str[:-2]) / 1024)
    try:
        return int(mem_str) // (1024 * 1024)  # assume bytes
    except ValueError:
        return 0


async def create_container(
    name: str,
    image: str = "images:debian/bookworm",
    memory_limit: str = "2GB",
    cpu_limit: int = 2,
) -> dict:
    """Create and start a new LXC container."""
    code, output = await _run(
        ["incus", "launch", image, name], timeout=300,
    )
    if code != 0:
        return {"success": False, "error": output}

    # Set resource limits
    await _run(["incus", "config", "set", name, "limits.memory", memory_limit])
    await _run(["incus", "config", "set", name, "limits.cpu", str(cpu_limit)])

    return {"success": True, "name": name}


async def exec_in_container(name: str, cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    """Execute a command inside a container."""
    return await _run(["incus", "exec", name, "--"] + cmd, timeout=timeout)


async def push_file(name: str, local_path: str, remote_path: str) -> tuple[int, str]:
    """Push a file into a container."""
    return await _run(["incus", "file", "push", local_path, f"{name}{remote_path}"])


async def start_container(name: str) -> dict:
    code, output = await _run(["incus", "start", name])
    return {"success": code == 0, "output": output}


async def stop_container(name: str) -> dict:
    code, output = await _run(["incus", "stop", name])
    return {"success": code == 0, "output": output}


async def restart_container(name: str) -> dict:
    code, output = await _run(["incus", "restart", name])
    return {"success": code == 0, "output": output}


async def destroy_container(name: str) -> dict:
    """Stop and delete a container."""
    await _run(["incus", "stop", name, "--force"])
    code, output = await _run(["incus", "delete", name, "--force"])
    return {"success": code == 0, "output": output}


async def get_container_logs(name: str, lines: int = 100) -> str:
    """Get recent logs from a container's journal."""
    code, output = await exec_in_container(
        name, ["journalctl", "--no-pager", "-n", str(lines)], timeout=30,
    )
    return output if code == 0 else f"Error getting logs: {output}"
