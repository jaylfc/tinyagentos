from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from tinyagentos.installers.base import AppInstaller, run_cmd


class DockerInstaller(AppInstaller):
    def __init__(self, apps_dir: Path | None = None):
        self.apps_dir = apps_dir or Path("/opt/tinyagentos/apps")

    def _compose_path(self, app_id: str) -> Path:
        return self.apps_dir / app_id / "docker-compose.yaml"

    def _generate_compose(self, app_id: str, install_config: dict) -> dict:
        """Generate a docker-compose.yaml from the manifest install config."""
        service = {
            "image": install_config["image"],
            "restart": "unless-stopped",
        }
        if "volumes" in install_config:
            service["volumes"] = install_config["volumes"]
        if "env" in install_config:
            service["environment"] = install_config["env"]
        if "ports" in install_config.get("requires", {}):
            service["ports"] = [f"{p}:{p}" for p in install_config["requires"]["ports"]]
        elif "ports" in install_config:
            service["ports"] = [f"{p}:{p}" for p in install_config["ports"]]

        return {
            "version": "3.8",
            "services": {app_id: service},
        }

    async def install(self, app_id: str, install_config: dict, **kwargs) -> dict:
        app_dir = self.apps_dir / app_id
        app_dir.mkdir(parents=True, exist_ok=True)

        compose = self._generate_compose(app_id, install_config)
        compose_path = self._compose_path(app_id)
        compose_path.write_text(yaml.dump(compose, default_flow_style=False))

        # Pull image
        code, output = await run_cmd(
            ["docker", "compose", "-f", str(compose_path), "pull"],
            cwd=str(app_dir),
        )
        if code != 0:
            return {"success": False, "error": f"docker pull failed: {output}"}

        return {"success": True, "path": str(app_dir)}

    async def uninstall(self, app_id: str) -> dict:
        compose_path = self._compose_path(app_id)
        if compose_path.exists():
            await run_cmd(
                ["docker", "compose", "-f", str(compose_path), "down", "-v"],
                cwd=str(compose_path.parent),
            )
        app_dir = self.apps_dir / app_id
        if app_dir.exists():
            shutil.rmtree(app_dir)
        return {"success": True}

    async def start(self, app_id: str) -> dict:
        compose_path = self._compose_path(app_id)
        if not compose_path.exists():
            return {"success": False, "error": "docker-compose.yaml not found"}
        code, output = await run_cmd(
            ["docker", "compose", "-f", str(compose_path), "up", "-d"],
            cwd=str(compose_path.parent),
        )
        return {"success": code == 0, "output": output}

    async def stop(self, app_id: str) -> dict:
        compose_path = self._compose_path(app_id)
        if not compose_path.exists():
            return {"success": False, "error": "docker-compose.yaml not found"}
        code, output = await run_cmd(
            ["docker", "compose", "-f", str(compose_path), "down"],
            cwd=str(compose_path.parent),
        )
        return {"success": code == 0, "output": output}
