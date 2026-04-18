"""System prompt assembly — layered pieces → single string."""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STRICT_READ_DIRECTIVE = (
    "Read this document end-to-end. Do not skim, summarise, or truncate. "
    "Every section below is load-bearing."
)

_SEPARATOR = "\n\n---\n\n"


def _load_agent_rules() -> str:
    """Read `docs/agent-rules.md` from the installed taosmd package.

    Falls back to empty string with a warning log if the file is missing —
    agents still boot, but without the memory-usage contract.
    """
    try:
        import taosmd
    except ImportError:
        logger.warning("taosmd not installed — skipping agent-rules block")
        return ""
    pkg_root = Path(taosmd.__file__).resolve().parent.parent
    rules_path = pkg_root / "docs" / "agent-rules.md"
    if not rules_path.exists():
        logger.warning("taosmd agent-rules.md missing at %s", rules_path)
        return ""
    return rules_path.read_text(encoding="utf-8")


def _taosmd_agent_rules(slug: str) -> str:
    raw = _load_agent_rules()
    if not raw:
        return ""
    return raw.replace("<your-agent-name>", slug)


def assemble_system_prompt(agent) -> str:
    """Assemble the agent's system prompt from its record fields.

    Pure function — call every turn rather than caching.
    """
    parts: list[str] = [STRICT_READ_DIRECTIVE]
    if getattr(agent, "memory_plugin", "taosmd") == "taosmd":
        rules = _taosmd_agent_rules(agent.slug)
        if rules:
            parts.append(rules)
    if getattr(agent, "soul_md", ""):
        parts.append(agent.soul_md)
    if getattr(agent, "agent_md", ""):
        parts.append(agent.agent_md)
    return _SEPARATOR.join(parts)
