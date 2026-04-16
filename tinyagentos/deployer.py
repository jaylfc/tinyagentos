"""Agent deployment — create container, install framework, start.

Honours the framework-agnostic runtime rule: containers hold code, hosts
hold state. See ``docs/design/framework-agnostic-runtime.md``. This
deployer installs only the agent framework into the container. Memory,
workspace, secrets, and the embedding service all live on the host and
reach the container via bind mounts or injected service URLs.

A container produced by this deployer can be destroyed and rebuilt from
the image with zero user-visible state loss, which is the whole point.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from tinyagentos.containers import (
    create_container, exec_in_container,
    start_container, stop_container, destroy_container,
)

logger = logging.getLogger(__name__)


@dataclass
class DeployRequest:
    name: str
    framework: str        # agent framework app_id
    model: str | None     # model app_id (optional)
    data_dir: Path        # host data dir — all per-agent state lives under here
    color: str = "#888888"
    memory_limit: str | None = None
    cpu_limit: int | None = None
    extra_config: dict | None = None
    can_read_user_memory: bool = False
    taos_host: str = "host.docker.internal"
    taos_port: int = 6969


async def deploy_agent(req: DeployRequest) -> dict:
    """Full agent deployment: create container → install framework → start.

    Rolls back (destroys container) on any critical failure after creation.
    No per-agent state is written inside the container — everything the
    agent needs reaches it via bind mounts (``/workspace``, ``/memory``)
    or injected service URL env vars (LLM proxy, embeddings, skills, user
    memory). Destroying and re-running this on the same name is safe.
    """
    import asyncio

    container_name = f"taos-agent-{req.name}"
    steps = []

    # Per-agent host-side state directories. These are the mounts the
    # container sees at /workspace and /memory. Created if missing so the
    # first deploy of a new agent just works.
    host_workspace = req.data_dir / "agent-workspaces" / req.name
    host_memory = req.data_dir / "agent-memory" / req.name
    host_workspace.mkdir(parents=True, exist_ok=True)
    host_memory.mkdir(parents=True, exist_ok=True)

    mounts = [
        (str(host_workspace), "/workspace"),
        (str(host_memory), "/memory"),
    ]

    # Env vars injected at container creation time — all point at host
    # services so the container holds zero config it would lose on rebuild.
    env: dict[str, str] = {}

    # LLM proxy (LiteLLM). The proxy is also the embedding endpoint in the
    # default configuration: LiteLLM exposes POST /v1/embeddings and will
    # route to whichever embedding model the host catalog configures.
    llm_key = None
    if req.extra_config and req.extra_config.get("llm_proxy"):
        proxy = req.extra_config["llm_proxy"]
        if proxy.is_running():
            llm_key = await proxy.create_agent_key(req.name)
            if llm_key:
                from tinyagentos.llm_proxy import EMBEDDING_ALIAS
                env["OPENAI_API_KEY"] = llm_key
                env["OPENAI_BASE_URL"] = f"{proxy.url}/v1"
                # Host-side embedding endpoint — same LiteLLM process,
                # OpenAI-compatible /v1/embeddings. Framework-agnostic.
                env["TAOS_EMBEDDING_URL"] = f"{proxy.url}/v1/embeddings"
                # Stable alias the host LiteLLM routes to whichever
                # concrete embedding model the backends actually have
                # loaded. Agents pick this up and pass it as the `model`
                # field of their embedding requests.
                env["TAOS_EMBEDDING_MODEL"] = EMBEDDING_ALIAS

    # User memory (optional, permission-gated)
    if req.can_read_user_memory:
        env["TAOS_USER_MEMORY_URL"] = (
            f"http://{req.taos_host}:{req.taos_port}"
            f"/api/user-memory/agent-search?agent_name={req.name}"
        )

    # Skill runtime — all skill execution happens on the host via the
    # in-process Skill MCP server. Container just needs the URL.
    skill_server_url = f"http://{req.taos_host}:{req.taos_port}/api/skill-exec"
    env["TAOS_SKILLS_URL"] = skill_server_url
    env["TAOS_SKILLS_MCP_URL"] = skill_server_url
    env["TAOS_SKILLS_TOOLS_URL"] = (
        f"{skill_server_url}/tools?agent_name={req.name}"
    )
    env["TAOS_AGENT_NAME"] = req.name

    # Step 1: Create container with mounts + env baked in at launch time
    logger.info(f"Creating container {container_name}")
    result = await create_container(
        container_name,
        image="images:debian/bookworm",
        memory_limit=req.memory_limit,
        cpu_limit=req.cpu_limit,
        mounts=mounts,
        env=env,
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

        # Step 3: Install base dependencies (framework needs these)
        logger.info(f"Installing dependencies in {container_name}")
        code, output = await exec_in_container(
            container_name,
            ["bash", "-c", "apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-venv git curl"],
            timeout=600,
        )
        if code != 0:
            raise RuntimeError(f"Dependency install failed: {output}")
        steps.append("deps_installed")

        # Step 4: Install agent framework (if specified and not just "none").
        # This is the only thing beyond the base OS that lives in the image.
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

        # Step 5: Get container IP
        code, output = await exec_in_container(container_name, ["hostname", "-I"])
        container_ip = output.strip().split()[0] if code == 0 and output.strip() else None
        steps.append("deployment_complete")

        return {
            "success": True,
            "name": req.name,
            "container": container_name,
            "ip": container_ip,
            "llm_key": llm_key,
            "steps": steps,
        }

    except Exception as exc:
        logger.error(f"Deploy failed at step {steps[-1] if steps else 'init'}: {exc}")
        logger.info(f"Rolling back: destroying container {container_name}")
        await destroy_container(container_name)
        steps.append("rolled_back")
        return {"success": False, "error": str(exc), "steps": steps}


async def undeploy_agent(name: str) -> dict:
    """Stop and destroy an agent's container.

    Host-side state (workspace, memory, secret grants) is left alone — the
    rule says containers are disposable, state is the identity. Rerun
    ``deploy_agent`` with the same name to bring the agent back exactly as
    it was. Use a separate ``delete_agent`` flow to also remove host state.
    """
    container_name = f"taos-agent-{name}"
    result = await destroy_container(container_name)
    return {"success": result["success"], "name": name}
