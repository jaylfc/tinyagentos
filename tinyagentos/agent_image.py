"""Pre-built agent base image management.

Fresh agent deploys used to spend ~60-90s per container doing work that
is identical for every openclaw agent on a given arch: apt install Node
/ curl, download openclaw tarball, npm install, systemd unit scaffolding.

Under this module a prebuilt LXC image (`taos-openclaw-base`) published
by ``.github/workflows/build-agent-images.yml`` is imported once per
host. The deployer then launches containers from that alias instead of
``images:debian/bookworm`` and install.sh skips the heavy steps.

The helpers here are deliberately small wrappers around ``incus`` so
the deployer can ask "is the base image already imported?" without
pulling in the full container backend abstraction.
"""
from __future__ import annotations

import asyncio
import logging
import platform

logger = logging.getLogger(__name__)

# Tag + asset naming must match the workflow at
# .github/workflows/build-agent-images.yml. Both must move together.
BASE_IMAGE_ALIAS = "taos-openclaw-base"
RELEASE_BASE_URL = (
    "https://github.com/jaylfc/tinyagentos/releases/download/rolling-images"
)


def arch_suffix() -> str:
    """Return the tarball arch suffix matching the workflow matrix.

    Aligns with openclaw's fork CI naming so there is a single arch
    vocabulary across tooling: ``arm64`` or ``x64``.
    """
    machine = platform.machine().lower()
    if machine in ("aarch64", "arm64"):
        return "arm64"
    if machine in ("x86_64", "amd64"):
        return "x64"
    return machine or "unknown"


def base_image_url(arch: str | None = None) -> str:
    """URL of the published image tarball for ``arch`` (defaults to host arch)."""
    return f"{RELEASE_BASE_URL}/{BASE_IMAGE_ALIAS}-linux-{arch or arch_suffix()}.tar.gz"


async def is_image_present(alias: str = BASE_IMAGE_ALIAS) -> bool:
    """Return True iff incus already has an image with this alias locally.

    Uses ``incus image list --format=csv -c f --filter=alias=<alias>`` and
    checks the output has any non-empty row. Any failure (incus not
    installed, daemon down) returns False — the caller will fall back to
    the uncached deploy path.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "incus", "image", "list",
            "--format=csv", "-c", "f",
            f"--filter=alias={alias}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
    except (FileNotFoundError, asyncio.TimeoutError):
        return False
    except Exception:  # pragma: no cover - defensive
        return False
    if proc.returncode != 0:
        return False
    for line in (stdout or b"").decode().splitlines():
        if line.strip():
            return True
    return False


async def ensure_image_present(
    alias: str = BASE_IMAGE_ALIAS,
    url: str | None = None,
) -> bool:
    """Import the base image from ``url`` if not already present.

    Non-fatal: returns True on success or already-present, False on any
    failure. The deployer retains a fallback path that launches from
    ``images:debian/bookworm`` so a missing cache image never blocks deploys.

    This is intended as a one-time bootstrap called from app startup.
    The image is ~300-500 MB so expect this to take a minute on first
    run; subsequent taOS boots are no-ops.

    Streams curl stdout directly into ``incus image import -``; no
    shell involved so the URL cannot be weaponised for injection.
    """
    if await is_image_present(alias):
        return True
    import_url = url or base_image_url()
    logger.info(
        "agent_image: importing base image %s from %s (one-time bootstrap, ~300-500MB)",
        alias, import_url,
    )
    try:
        curl = await asyncio.create_subprocess_exec(
            "curl", "-fsSL", "--max-time", "600", import_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        incus = await asyncio.create_subprocess_exec(
            "incus", "image", "import", "-", "--alias", alias,
            stdin=curl.stdout,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        # Close our handle so incus sees EOF when curl finishes.
        if curl.stdout is not None:
            curl.stdout.close()
        incus_out, _ = await asyncio.wait_for(incus.communicate(), timeout=900)
        curl_rc = await asyncio.wait_for(curl.wait(), timeout=30)
    except (FileNotFoundError, asyncio.TimeoutError) as exc:
        logger.warning("agent_image: import failed for %s: %s", alias, exc)
        return False
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("agent_image: import failed for %s: %s", alias, exc)
        return False
    if curl_rc != 0:
        logger.warning(
            "agent_image: curl for %s exited %s (is the image published yet?)",
            alias, curl_rc,
        )
        return False
    if incus.returncode != 0:
        logger.warning(
            "agent_image: incus image import of %s returned %s: %s",
            alias, incus.returncode, (incus_out or b"").decode()[:500],
        )
        return False
    logger.info("agent_image: %s imported OK", alias)
    return True


__all__ = [
    "BASE_IMAGE_ALIAS",
    "RELEASE_BASE_URL",
    "arch_suffix",
    "base_image_url",
    "is_image_present",
    "ensure_image_present",
]
