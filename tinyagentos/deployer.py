"""Agent deployment — create LXC container, install framework + QMD, configure, start."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from tinyagentos.containers import (
    create_container, exec_in_container, push_file,
    start_container, stop_container, destroy_container,
)

logger = logging.getLogger(__name__)

# Systemd service template for qmd serve inside agent container
QMD_SERVICE = """[Unit]
Description=QMD Serve (Agent Memory)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/qmd serve --port 7832 --bind {bind} --backend rkllama --rkllama-url {rkllama_url}
Restart=on-failure
RestartSec=5
Environment=NODE_ENV=production
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
"""


@dataclass
class DeployRequest:
    name: str
    framework: str        # agent framework app_id
    model: str | None     # model app_id (optional)
    color: str = "#888888"
    memory_limit: str = "2GB"
    cpu_limit: int = 2
    rkllama_url: str = "http://100.78.225.80:8080"
    extra_config: dict | None = None


async def deploy_agent(req: DeployRequest) -> dict:
    """Full agent deployment: create container → install deps → configure → start.
    Rolls back (destroys container) on any critical failure after creation."""
    import asyncio
    import tempfile

    container_name = f"agent-{req.name}"
    steps = []

    # Step 1: Create container
    logger.info(f"Creating container {container_name}")
    result = await create_container(
        container_name,
        image="images:debian/bookworm",
        memory_limit=req.memory_limit,
        cpu_limit=req.cpu_limit,
    )
    if not result["success"]:
        return {"success": False, "error": f"Container creation failed: {result.get('error')}", "steps": steps}
    steps.append("container_created")

    try:
        # Step 2: Wait for network
        for _ in range(10):
            code, output = await exec_in_container(container_name, ["hostname", "-I"])
            if code == 0 and output.strip():
                break
            await asyncio.sleep(2)
        steps.append("network_ready")

        # Step 3: Install base dependencies
        logger.info(f"Installing dependencies in {container_name}")
        code, output = await exec_in_container(
            container_name,
            ["bash", "-c", "apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-venv nodejs npm git curl"],
            timeout=600,
        )
        if code != 0:
            raise RuntimeError(f"Dependency install failed: {output}")
        steps.append("deps_installed")

        # Step 4: Install QMD
        logger.info(f"Installing QMD in {container_name}")
        code, output = await exec_in_container(
            container_name,
            ["npm", "install", "-g", "github:jaylfc/qmd#feat/remote-llm-provider"],
            timeout=300,
        )
        if code != 0:
            logger.warning(f"QMD install warning: {output}")
        steps.append("qmd_installed")

        # Step 5: Configure qmd serve systemd service
        # Bind to 0.0.0.0 inside container so the host can reach it
        qmd_service_content = QMD_SERVICE.format(bind="0.0.0.0", rkllama_url=req.rkllama_url)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".service", delete=False) as f:
            f.write(qmd_service_content)
            tmp_path = f.name
        await push_file(container_name, tmp_path, "/etc/systemd/system/qmd-serve.service")
        Path(tmp_path).unlink()
        await exec_in_container(container_name, ["systemctl", "daemon-reload"])
        await exec_in_container(container_name, ["systemctl", "enable", "qmd-serve"])
        await exec_in_container(container_name, ["systemctl", "start", "qmd-serve"])
        steps.append("qmd_serve_configured")

        # Step 6: Install agent framework (if specified and not just "none")
        if req.framework and req.framework != "none":
            logger.info(f"Installing framework {req.framework} in {container_name}")
            code, output = await exec_in_container(
                container_name,
                ["pip3", "install", req.framework],
                timeout=300,
            )
            if code != 0:
                logger.warning(f"Framework install warning: {output}")
            steps.append("framework_installed")

        # Step 7: Get container IP
        code, output = await exec_in_container(container_name, ["hostname", "-I"])
        container_ip = output.strip().split()[0] if code == 0 and output.strip() else None
        steps.append("deployment_complete")

        return {
            "success": True,
            "name": req.name,
            "container": container_name,
            "ip": container_ip,
            "qmd_url": f"http://{container_ip}:7832" if container_ip else None,
            "steps": steps,
        }

    except Exception as exc:
        logger.error(f"Deploy failed at step {steps[-1] if steps else 'init'}: {exc}")
        logger.info(f"Rolling back: destroying container {container_name}")
        await destroy_container(container_name)
        steps.append("rolled_back")
        return {"success": False, "error": str(exc), "steps": steps}


async def undeploy_agent(name: str) -> dict:
    """Stop and destroy an agent's container."""
    container_name = f"agent-{name}"
    result = await destroy_container(container_name)
    return {"success": result["success"], "name": name}
