from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

from tinyagentos.installers.base import AppInstaller


async def download_file(url: str, dest: Path, expected_sha256: str | None = None) -> Path:
    """Download a file with optional SHA256 verification."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            sha = hashlib.sha256()
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)
                    sha.update(chunk)
    if expected_sha256 and sha.hexdigest() != expected_sha256:
        dest.unlink()
        raise ValueError(f"SHA256 mismatch: expected {expected_sha256}, got {sha.hexdigest()}")
    return dest


class DownloadInstaller(AppInstaller):
    def __init__(self, models_dir: Path | None = None):
        self.models_dir = models_dir or Path("/opt/tinyagentos/models")

    async def install(self, app_id: str, install_config: dict, variant: dict | None = None, **kwargs) -> dict:
        if not variant:
            return {"success": False, "error": "variant required for model download"}

        filename = f"{app_id}-{variant['id']}.{variant.get('format', 'bin')}"
        dest = self.models_dir / filename

        if dest.exists():
            return {"success": True, "path": str(dest), "cached": True}

        try:
            path = await download_file(
                url=variant["download_url"],
                dest=dest,
                expected_sha256=variant.get("sha256"),
            )
            return {"success": True, "path": str(path)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def uninstall(self, app_id: str, variant_id: str | None = None, **kwargs) -> dict:
        # Delete matching model files
        deleted = []
        for f in self.models_dir.glob(f"{app_id}*"):
            if variant_id and variant_id not in f.name:
                continue
            f.unlink()
            deleted.append(f.name)
        return {"success": True, "deleted": deleted}
