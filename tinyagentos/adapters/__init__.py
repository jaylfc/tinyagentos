"""Adapter registry — maps framework IDs to metadata and verification status."""
from __future__ import annotations

# Each entry describes one adapter that ships with TinyAgentOS.
# verification_status values:
#   tested       -- validated end-to-end on real hardware with real agents
#   beta         -- basic integration working; some edge cases unverified
#   experimental -- adapter exists, happy path only, not battle-tested
#   broken       -- known to be non-functional on current codebase
_REGISTRY: list[dict] = [
    {
        "id": "smolagents",
        "name": "SmolAgents",
        "description": "Lightweight code-first agent framework by Hugging Face",
        "verification_status": "tested",
    },
    {
        "id": "generic",
        "name": "Generic",
        "description": "Fallback adapter — echos messages; use as a starting point",
        "verification_status": "tested",
    },
    {
        "id": "openclaw",
        "name": "OpenClaw",
        "description": "OpenClaw LXC-native agent via HTTP proxy",
        "verification_status": "beta",
    },
    {
        "id": "pocketflow",
        "name": "PocketFlow",
        "description": "Graph-based flow execution with OpenAI-compatible backend",
        "verification_status": "beta",
    },
    {
        "id": "langroid",
        "name": "Langroid",
        "description": "Task-based multi-agent framework using Langroid ChatAgent",
        "verification_status": "beta",
    },
    {
        "id": "openai-agents-sdk",
        "name": "OpenAI Agents SDK",
        "description": "OpenAI Agents SDK with Runner.run_sync",
        "verification_status": "beta",
    },
    {
        "id": "agent_zero",
        "name": "Agent Zero",
        "description": "Proxies messages to the Agent Zero HTTP API",
        "verification_status": "experimental",
    },
    {
        "id": "hermes",
        "name": "Hermes",
        "description": "Hermes OpenAI-compatible API bridge (bridge wiring not yet complete)",
        "verification_status": "experimental",
    },
    {
        "id": "ironclaw",
        "name": "IronClaw",
        "description": "IronClaw gateway proxy",
        "verification_status": "experimental",
    },
    {
        "id": "microclaw",
        "name": "MicroClaw",
        "description": "MicroClaw gateway proxy",
        "verification_status": "experimental",
    },
    {
        "id": "moltis",
        "name": "Moltis",
        "description": "Moltis gateway proxy",
        "verification_status": "experimental",
    },
    {
        "id": "nanoclaw",
        "name": "NanoClaw",
        "description": "NanoClaw gateway proxy",
        "verification_status": "experimental",
    },
    {
        "id": "nullclaw",
        "name": "NullClaw",
        "description": "NullClaw gateway proxy",
        "verification_status": "experimental",
    },
    {
        "id": "picoclaw",
        "name": "PicoClaw",
        "description": "PicoClaw gateway proxy",
        "verification_status": "experimental",
    },
    {
        "id": "shibaclaw",
        "name": "ShibaClaw",
        "description": "ShibaClaw gateway proxy",
        "verification_status": "experimental",
    },
    {
        "id": "zeroclaw",
        "name": "ZeroClaw",
        "description": "ZeroClaw gateway proxy",
        "verification_status": "experimental",
    },
]

_VALID_STATUSES = {"tested", "beta", "experimental", "broken"}


def list_frameworks() -> list[dict]:
    """Return every registered adapter with id, name, description, and verification_status."""
    return [dict(entry) for entry in _REGISTRY]
