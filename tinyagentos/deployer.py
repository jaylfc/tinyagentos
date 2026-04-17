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

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from tinyagentos.containers import (
    create_container, exec_in_container, push_file,
    start_container, stop_container, destroy_container,
    add_proxy_device,
)

logger = logging.getLogger(__name__)


def _write_openclaw_bootstrap(
    *,
    host_home: Path,
    slug: str,
    llm_key: str | None,
    model: str | None,
    data_dir: Path,
    taos_host: str,
    taos_port: int,
) -> None:
    """Write openclaw.json + .openclaw/env into the agent-home host dir.

    The full agent-home dir is bind-mounted to /root inside the container,
    so the container sees these files at /root/.openclaw/... on first start.
    The openclaw systemd unit (written by install.sh) reads them via its
    EnvironmentFile directive and the gateway reads openclaw.json on startup.

    Called before create_container so the files exist by the time the
    container first runs install.sh and the systemd unit starts.
    """
    openclaw_dir = host_home / ".openclaw"
    openclaw_dir.mkdir(parents=True, exist_ok=True)
    openclaw_dir.chmod(0o700)

    # Bootstrap config: taos LiteLLM provider + gateway binding.
    config = {
        "gateway": {
            "bind": "loopback",
            "port": 18789,
            "auth": {
                "mode": "token",
            },
        },
        "channels": {},
        "models": {
            "providers": [
                {
                    "id": "taos",
                    "api": "openai-completions",
                    "baseUrl": f"http://127.0.0.1:4000/v1",
                    "apiKey": llm_key or "",
                    "default_model": model,
                }
            ]
        },
    }
    config_path = openclaw_dir / "openclaw.json"
    config_path.write_text(json.dumps(config, indent=2))

    # env file: bridge patch reads these on startup.
    local_token = ""
    try:
        token_path = data_dir / ".auth_local_token"
        if token_path.exists():
            local_token = token_path.read_text().strip()
    except Exception:
        pass

    env_lines = [
        f"TAOS_BRIDGE_URL=http://{taos_host}:{taos_port}",
        f"TAOS_LOCAL_TOKEN={local_token}",
        f"TAOS_AGENT_NAME={slug}",
    ]
    env_path = openclaw_dir / "env"
    env_path.write_text("\n".join(env_lines) + "\n")
    env_path.chmod(0o600)


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
    # Containers reach the host via incus proxy devices on the same port,
    # so 127.0.0.1 inside the container transparently forwards to
    # 127.0.0.1 on the host.
    taos_host: str = "127.0.0.1"
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
    # container sees at /workspace, /memory, and /root. Created if missing
    # so the first deploy of a new agent just works.
    host_workspace = req.data_dir / "agent-workspaces" / req.name
    host_memory = req.data_dir / "agent-memory" / req.name
    host_home = req.data_dir / "agent-home" / req.name
    host_workspace.mkdir(parents=True, exist_ok=True)
    host_memory.mkdir(parents=True, exist_ok=True)
    host_home.mkdir(parents=True, exist_ok=True)

    mounts = [
        (str(host_workspace), "/workspace"),
        (str(host_memory), "/memory"),
        (str(host_home), "/root"),
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
    # Agent's home folder is bind-mounted from the host so framework
    # configs, dotfiles, caches, and cloned repos persist across
    # container rebuilds and travel with the agent on archive / move.
    env["TAOS_AGENT_HOME"] = "/root"

    # Selected model name — the in-container agent runtime reads this
    # and passes it as the ``model`` field on LLM calls so the host's
    # LiteLLM proxy routes to the right backend.
    if req.model:
        env["TAOS_MODEL"] = req.model

    # Trace capture — local auth token + trace API URL so the container
    # runtime can POST events directly into the per-agent trace store.
    try:
        local_token_path = req.data_dir / ".auth_local_token"
        if local_token_path.exists():
            env["TAOS_LOCAL_TOKEN"] = local_token_path.read_text().strip()
    except Exception:
        pass
    env["TAOS_TRACE_URL"] = f"http://{req.taos_host}:{req.taos_port}/api/trace"

    # openclaw bootstrap: write openclaw.json + .openclaw/env into agent-home
    # host-side so they are visible inside the container at /root/.openclaw/
    # on first start (before install.sh runs, but consumed by the systemd unit
    # that install.sh writes).
    #
    # session_id == req.name (slug) for MVP. The bridge endpoints already key
    # their state on agent name, so minting a separate UUID adds no value at
    # this stage. A future task can promote it to a persisted UUID if needed.
    _write_openclaw_bootstrap(
        host_home=host_home,
        slug=req.name,
        llm_key=llm_key,
        model=req.model,
        data_dir=req.data_dir,
        taos_host=req.taos_host,
        taos_port=req.taos_port,
    )

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
        # Incus proxy devices: let the container reach host services via
        # its own 127.0.0.1. The openai SDK (pointed at OPENAI_BASE_URL)
        # and the skills / user-memory clients all hit localhost:<port>
        # inside the container — the deployer doesn't need to inject a
        # host IP or rely on DNS. If either add fails, bail: without
        # these the agent has no LLM and no host-side services.
        proxy_ports = [
            ("taos-proxy-litellm", 4000),
            ("taos-proxy-taos", req.taos_port),
        ]
        for dev_name, port in proxy_ports:
            res = await add_proxy_device(
                container_name,
                dev_name,
                listen=f"tcp:127.0.0.1:{port}",
                connect=f"tcp:127.0.0.1:{port}",
            )
            if not res.get("success"):
                raise RuntimeError(
                    f"failed to attach proxy device {dev_name}:{port}: {res.get('output', '')}"
                )
        steps.append("proxy_devices_attached")

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
            ["bash", "-c", "apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends python3 python3-pip python3-venv python3-dev git curl wget ca-certificates gnupg build-essential nodejs npm"],
            timeout=900,
        )
        if code != 0:
            raise RuntimeError(f"Dependency install failed: {output}")
        steps.append("deps_installed")

        # Step 4: Install agent framework (if specified and not just "none").
        # This is the only thing beyond the base OS that lives in the image.
        if req.framework and req.framework != "none":
            manifest = None
            if req.extra_config and req.extra_config.get("registry"):
                manifest = req.extra_config["registry"].get(req.framework)

            if manifest is None:
                # Fallback: no registry or manifest not found — pip install by framework id
                method = "pip"
                package = req.framework
            else:
                method = manifest.install.get("method")
                package = manifest.install.get("package")

            logger.info(f"Installing framework {req.framework} via {method} in {container_name}")

            if method == "pip":
                pkg = package if manifest is not None else req.framework
                code, output = await exec_in_container(
                    container_name,
                    ["pip3", "install", pkg],
                    timeout=300,
                )
                if code != 0:
                    raise RuntimeError(f"Framework install failed ({code}): {output[-500:]}")
            elif method == "script":
                script_name = manifest.install.get("script")
                script_path = manifest.manifest_dir / script_name
                if not script_path.exists():
                    raise RuntimeError(f"Install script missing: {script_path}")
                code, output = await push_file(
                    container_name, str(script_path), "/tmp/install.sh"
                )
                code, output = await exec_in_container(
                    container_name,
                    ["bash", "/tmp/install.sh"],
                    timeout=900,
                )
                if code != 0:
                    raise RuntimeError(f"Framework install failed ({code}): {output[-500:]}")
            else:
                raise RuntimeError(f"Unsupported install method: {method!r} for framework {req.framework}")

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


async def undeploy_agent(name: str, *, data_dir: Path | None = None, delete_state: bool = False) -> dict:
    """Stop and destroy an agent's container.

    Host-side state (workspace, memory, secret grants) is left alone by
    default — the rule says containers are disposable, state is the identity.
    Rerun ``deploy_agent`` with the same name to bring the agent back exactly
    as it was.

    When ``delete_state=True`` and ``data_dir`` is provided, this call also
    wipes the host-side workspace (``agent-workspaces/{name}``) and memory
    (``agent-memory/{name}``) directories. This is destructive and
    irreversible — only call it on a true delete, not a stop/rebuild flow.
    """
    container_name = f"taos-agent-{name}"
    result = await destroy_container(container_name)
    if delete_state and data_dir is not None:
        import shutil
        for sub in ("agent-workspaces", "agent-memory"):
            target = data_dir / sub / name
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
    return {"success": result["success"], "name": name}
