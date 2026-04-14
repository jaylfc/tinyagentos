from __future__ import annotations

import logging

from tinyagentos.mcp.permissions import check_permission
from tinyagentos.mcp.registry import MCPServerStore
from tinyagentos.mcp.supervisor import MCPSupervisor

logger = logging.getLogger(__name__)


async def call_tool(
    supervisor: MCPSupervisor,
    store: MCPServerStore,
    agent_name: str,
    agent_groups: list[str],
    server_id: str,
    tool: str,
    arguments: dict,
    resource: str | None = None,
) -> dict:
    result = await check_permission(
        store, server_id, agent_name, agent_groups, tool=tool, resource=resource
    )
    if not result.allowed:
        return {"error": "permission_denied", "reason": result.reason, "status": 403}

    if not supervisor.get_status(server_id)["running"]:
        started = await supervisor.start(server_id)
        if not started:
            return {"error": "server_unavailable", "reason": f"could not start {server_id}", "status": 503}

    logger.warning(
        "mcp proxy: actual MCP JSON-RPC call not yet wired — returning stub "
        "(server=%s tool=%s agent=%s)",
        server_id,
        tool,
        agent_name,
    )
    return {
        "ok": True,
        "result": "stub — MCP JSON-RPC call not yet wired",
        "tool": tool,
        "arguments": arguments,
    }
