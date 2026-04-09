"""Container backend abstraction layer."""
from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ContainerInfo:
    name: str
    status: str  # Running | Stopped | ...
    ip: str | None
    memory_mb: int
    cpu_cores: int


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


class ContainerBackend(ABC):
    """Abstract base class for container runtime backends."""

    @abstractmethod
    async def list_containers(self, prefix: str = "agent-") -> list[ContainerInfo]:
        """List all containers matching the given name prefix."""
        ...

    @abstractmethod
    async def create_container(
        self,
        name: str,
        image: str = "images:debian/bookworm",
        memory_limit: str = "2GB",
        cpu_limit: int = 2,
    ) -> dict:
        """Create and start a new container."""
        ...

    @abstractmethod
    async def exec_in_container(
        self, name: str, cmd: list[str], timeout: int = 300
    ) -> tuple[int, str]:
        """Execute a command inside a container."""
        ...

    @abstractmethod
    async def push_file(
        self, name: str, local_path: str, remote_path: str
    ) -> tuple[int, str]:
        """Push a file into a container."""
        ...

    @abstractmethod
    async def start_container(self, name: str) -> dict:
        """Start a stopped container."""
        ...

    @abstractmethod
    async def stop_container(self, name: str) -> dict:
        """Stop a running container."""
        ...

    @abstractmethod
    async def restart_container(self, name: str) -> dict:
        """Restart a container."""
        ...

    @abstractmethod
    async def destroy_container(self, name: str) -> dict:
        """Stop and delete a container."""
        ...

    @abstractmethod
    async def get_container_logs(self, name: str, lines: int = 100) -> str:
        """Get recent logs from a container."""
        ...


def detect_runtime() -> str:
    """Detect the available container runtime.

    Checks for incus, docker, podman in priority order.
    Returns 'lxc', 'docker', 'podman', or 'none'.
    """
    if shutil.which("incus"):
        return "lxc"
    if shutil.which("docker"):
        return "docker"
    if shutil.which("podman"):
        return "podman"
    return "none"


_active_backend: ContainerBackend | None = None


def get_backend() -> ContainerBackend:
    """Return the active container backend.

    Raises RuntimeError if no backend has been set.
    """
    if _active_backend is None:
        raise RuntimeError(
            "No container backend configured. Call set_backend() first."
        )
    return _active_backend


def set_backend(backend: ContainerBackend) -> None:
    """Set the active container backend."""
    global _active_backend
    _active_backend = backend
