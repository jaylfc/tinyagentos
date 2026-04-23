from __future__ import annotations

import logging
import secrets
import shlex
import socket
from contextlib import closing

from tinyagentos.installers.base import AppInstaller
import tinyagentos.containers as containers

logger = logging.getLogger(__name__)

# Gitea version pinned here; manifest may override via install_config["gitea_version"].
_DEFAULT_GITEA_VERSION = "1.22.6"

_SYSTEMD_UNIT = """\
[Unit]
Description=Gitea (Git with a cup of tea)
After=network.target

[Service]
RestartSec=2s
Type=simple
User=git
WorkingDirectory=/home/git
ExecStart=/usr/local/bin/gitea web -c /etc/gitea/app.ini
Restart=always
Environment=USER=git HOME=/home/git GITEA_WORK_DIR=/home/git

[Install]
WantedBy=multi-user.target
"""

_APP_INI_TEMPLATE = """\
[server]
HTTP_PORT = 3000
ROOT_URL = http://localhost:3000/
SSH_PORT = 2222

[database]
DB_TYPE = sqlite3
PATH = /home/git/gitea.db

[security]
INSTALL_LOCK = true
SECRET_KEY = {secret_key}
INTERNAL_TOKEN = {internal_token}

[service]
DISABLE_REGISTRATION = true
"""


def _render_app_ini() -> str:
    return _APP_INI_TEMPLATE.format(
        secret_key=secrets.token_hex(32),
        internal_token=secrets.token_hex(32),
    )


def _find_free_port(start: int = 13000, end: int = 14000) -> int:
    """Return the first available TCP port in [start, end)."""
    for port in range(start, end):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port found in range {start}-{end}")


class LXCInstaller(AppInstaller):
    """Install a service (e.g. Gitea) into an isolated incus/LXC container."""

    CONTAINER_PREFIX = "taos-svc-"

    def _container_name(self, app_id: str) -> str:
        return f"{self.CONTAINER_PREFIX}{app_id}"

    async def install(
        self,
        app_id: str,
        install_config: dict,
        *,
        admin_password: str,
        taos_username: str = "admin",
        taos_email: str = "",
        **kwargs,
    ) -> dict:
        """Install app_id into a new LXC container.

        Parameters
        ----------
        app_id:
            Catalog app identifier (used as container name suffix).
        install_config:
            ``install`` block from the manifest YAML.
        admin_password:
            Password for the initial service admin account. Required.
        taos_username:
            taOS username — becomes the Gitea admin username.
        taos_email:
            taOS user email — becomes the Gitea admin email.
        """
        if not admin_password:
            raise ValueError("admin_password is required for LXC installs")

        container_name = self._container_name(app_id)

        # Fail cleanly if container already exists.
        if await containers.container_exists(container_name):
            raise RuntimeError(
                f"Container '{container_name}' already exists. "
                "Uninstall first or choose a different app_id."
            )

        image = install_config.get("image", "images:debian/bookworm")
        memory_limit = install_config.get("memory_limit", "512MiB")
        cpu_limit = int(install_config.get("cpu_limit", 1))
        gitea_version = install_config.get("gitea_version", _DEFAULT_GITEA_VERSION)

        # Step 1: Create container.
        logger.info("LXCInstaller: creating container %s from %s", container_name, image)
        result = await containers.create_container(
            container_name,
            image=image,
            memory_limit=memory_limit,
            cpu_limit=cpu_limit,
        )
        if not result.get("success"):
            raise RuntimeError(f"Container creation failed: {result.get('error', '')}")

        try:
            # Step 2: Wait for network readiness.
            import asyncio
            for _ in range(15):
                code, output = await containers.exec_in_container(
                    container_name, ["hostname", "-I"], timeout=10
                )
                if code == 0 and output.strip():
                    break
                await asyncio.sleep(2)
            else:
                raise RuntimeError("Container did not get a network address in time")

            # Step 3: Install base packages and create git system user.
            logger.info("LXCInstaller: installing packages in %s", container_name)
            code, output = await containers.exec_in_container(
                container_name,
                [
                    "bash", "-c",
                    "apt-get update -qq && "
                    "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "
                    "--no-install-recommends git sqlite3 wget ca-certificates && "
                    "useradd --system --create-home --shell /bin/bash git",
                ],
                timeout=300,
            )
            if code != 0:
                raise RuntimeError(f"Package install failed: {output}")

            # Step 4: Download Gitea binary (auto-detect arch).
            logger.info("LXCInstaller: downloading Gitea %s", gitea_version)
            code, output = await containers.exec_in_container(
                container_name,
                [
                    "bash", "-c",
                    f"ARCH=$(dpkg --print-architecture) && "
                    f"wget -q -O /usr/local/bin/gitea "
                    f"https://dl.gitea.com/gitea/{gitea_version}/gitea-{gitea_version}-linux-${{ARCH}} && "
                    f"chmod +x /usr/local/bin/gitea",
                ],
                timeout=300,
            )
            if code != 0:
                raise RuntimeError(f"Gitea download failed: {output}")

            # Step 5: Write config and systemd unit.
            logger.info("LXCInstaller: writing config and systemd unit")
            code, output = await containers.exec_in_container(
                container_name,
                ["bash", "-c", "mkdir -p /etc/gitea && chmod 770 /etc/gitea"],
            )
            if code != 0:
                raise RuntimeError(f"Failed to create /etc/gitea: {output}")

            # Write app.ini (generate fresh secrets per install)
            app_ini = _render_app_ini()
            code, output = await containers.exec_in_container(
                container_name,
                ["bash", "-c", f"cat > /etc/gitea/app.ini << 'TAOS_EOF'\n{app_ini}\nTAOS_EOF"],
            )
            if code != 0:
                raise RuntimeError(f"Failed to write app.ini: {output}")

            # Write systemd unit
            code, output = await containers.exec_in_container(
                container_name,
                ["bash", "-c", f"cat > /etc/systemd/system/gitea.service << 'TAOS_EOF'\n{_SYSTEMD_UNIT}\nTAOS_EOF"],
            )
            if code != 0:
                raise RuntimeError(f"Failed to write systemd unit: {output}")

            # Step 6: First-boot DB migration + admin user creation.
            logger.info("LXCInstaller: running Gitea DB migration")
            code, output = await containers.exec_in_container(
                container_name,
                ["su", "-", "git", "-c", "GITEA_WORK_DIR=/home/git gitea migrate -c /etc/gitea/app.ini"],
                timeout=120,
            )
            if code != 0:
                raise RuntimeError(f"Gitea migrate failed: {output}")

            logger.info("LXCInstaller: creating Gitea admin user '%s'", taos_username)
            safe_username = shlex.quote(taos_username)
            safe_email = shlex.quote(taos_email or taos_username + "@localhost")
            safe_password = shlex.quote(admin_password)
            code, output = await containers.exec_in_container(
                container_name,
                [
                    "su", "-", "git", "-c",
                    f"GITEA_WORK_DIR=/home/git gitea admin user create "
                    f"--admin "
                    f"--username {safe_username} "
                    f"--email {safe_email} "
                    f"--password {safe_password} "
                    f"--must-change-password=false "
                    f"-c /etc/gitea/app.ini",
                ],
                timeout=60,
            )
            if code != 0:
                raise RuntimeError(f"Gitea admin user creation failed: {output}")

            # Step 7: Enable and start service.
            logger.info("LXCInstaller: enabling and starting gitea.service")
            code, output = await containers.exec_in_container(
                container_name,
                ["bash", "-c", "systemctl daemon-reload && systemctl enable gitea && systemctl start gitea"],
                timeout=60,
            )
            if code != 0:
                raise RuntimeError(f"Failed to start gitea service: {output}")

            # Step 8: Add proxy device (host_port → container:3000).
            host_port = _find_free_port()
            logger.info(
                "LXCInstaller: adding proxy device host:%d -> container:3000", host_port
            )
            res = await containers.add_proxy_device(
                container_name,
                device_name="gitea-http",
                listen=f"tcp:0.0.0.0:{host_port}",
                connect="tcp:127.0.0.1:3000",
            )
            if not res.get("success"):
                raise RuntimeError(
                    f"Failed to add proxy device: {res.get('output', '')}"
                )

            # Step 9: Record install metadata.
            install_record = {
                "app_id": app_id,
                "backend": "lxc",
                "container": container_name,
                "host_port": host_port,
                "gitea_version": gitea_version,
                "admin_username": taos_username,
            }
            logger.info("LXCInstaller: install complete — %s", install_record)
            return {"success": True, **install_record}

        except Exception:
            logger.exception(
                "LXCInstaller: rolling back — destroying container %s", container_name
            )
            await containers.destroy_container(container_name)
            raise

    async def uninstall(self, app_id: str) -> dict:
        """Stop and delete the service container."""
        container_name = self._container_name(app_id)
        result = await containers.destroy_container(container_name)
        return {"success": result["success"], "app_id": app_id}

    async def start(self, app_id: str) -> dict:
        container_name = self._container_name(app_id)
        result = await containers.start_container(container_name)
        return result

    async def stop(self, app_id: str) -> dict:
        container_name = self._container_name(app_id)
        result = await containers.stop_container(container_name)
        return result
