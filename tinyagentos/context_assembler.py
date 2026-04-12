"""Context Window Assembler (taOSmd).

Inspired by MemPalace's L0-L3 layer system and Letta's virtual context memory.
Assembles the optimal context for an agent's LLM call by pulling from multiple
memory layers based on relevance and token budget.

Layers:
  L0: Identity — who is the agent, who is the user (~100 tokens, always loaded)
  L1: Active facts — current KG facts about the user + project (~200 tokens)
  L2: Relevant memories — semantic search results from recent context (~500 tokens)
  L3: Deep recall — archive search, full KG traversal (on-demand, ~1000 tokens)

Total context budget is configurable. Each layer has a soft token limit.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tinyagentos.temporal_knowledge_graph import TemporalKnowledgeGraph
    from tinyagentos.archive import ArchiveStore

logger = logging.getLogger(__name__)

# Rough token estimation: 1 token ≈ 4 chars
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Rough token count estimate."""
    return len(text) // CHARS_PER_TOKEN


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to approximately max_tokens."""
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


class ContextAssembler:
    """Assembles agent context from multiple memory layers."""

    def __init__(
        self,
        kg: TemporalKnowledgeGraph | None = None,
        archive: ArchiveStore | None = None,
        qmd_base_url: str = "http://localhost:7832",
        http_client=None,
    ):
        self._kg = kg
        self._archive = archive
        self._qmd_url = qmd_base_url
        self._http = http_client

    # ------------------------------------------------------------------
    # L0: Identity
    # ------------------------------------------------------------------

    async def assemble_l0(
        self,
        agent_name: str | None = None,
        user_name: str | None = None,
        system_info: dict | None = None,
        max_tokens: int = 100,
    ) -> str:
        """Always-loaded identity context. ~100 tokens."""
        parts = []

        if agent_name:
            parts.append(f"You are {agent_name}, an AI agent running on taOS.")
        if user_name:
            parts.append(f"Your user is {user_name}.")
        if system_info:
            hw = []
            if system_info.get("cpu"):
                hw.append(system_info["cpu"])
            if system_info.get("npu"):
                hw.append(f"NPU: {system_info['npu']}")
            if system_info.get("ram"):
                hw.append(f"RAM: {system_info['ram']}")
            if hw:
                parts.append(f"Hardware: {', '.join(hw)}.")

        text = " ".join(parts)
        return truncate_to_tokens(text, max_tokens)

    # ------------------------------------------------------------------
    # L1: Active Knowledge Graph Facts
    # ------------------------------------------------------------------

    async def assemble_l1(
        self,
        user_name: str | None = None,
        agent_name: str | None = None,
        project: str | None = None,
        max_tokens: int = 200,
    ) -> str:
        """Current facts from the knowledge graph. ~200 tokens."""
        if not self._kg:
            return ""

        parts = []
        entities_to_query = []
        if user_name:
            entities_to_query.append(user_name)
        if agent_name:
            entities_to_query.append(agent_name)
        if project:
            entities_to_query.append(project)

        for entity in entities_to_query:
            try:
                results = await self._kg.query_entity(entity, direction="outgoing")
                for r in results[:5]:  # Top 5 facts per entity
                    parts.append(f"{entity} {r['predicate']} {r.get('object_name', '?')}")
            except Exception:
                pass

        if not parts:
            return ""

        text = "Known facts:\n" + "\n".join(f"- {p}" for p in parts)
        return truncate_to_tokens(text, max_tokens)

    # ------------------------------------------------------------------
    # L2: Relevant Recent Context
    # ------------------------------------------------------------------

    async def assemble_l2(
        self,
        query: str,
        agent_name: str | None = None,
        max_tokens: int = 500,
    ) -> str:
        """Semantic search + recent archive for the current query. ~500 tokens."""
        parts = []

        # Search archive for recent relevant events
        if self._archive:
            try:
                events = await self._archive.query(
                    agent_name=agent_name,
                    search=query,
                    limit=5,
                )
                for e in events:
                    summary = e.get("summary", "")
                    if summary:
                        parts.append(f"[{e['event_type']}] {summary}")
            except Exception:
                pass

        # Search KG for related entities
        if self._kg:
            words = query.split()
            for word in words:
                if len(word) < 3:
                    continue
                try:
                    results = await self._kg.query_entity(word)
                    for r in results[:2]:
                        obj = r.get("object_name") or r.get("subject_name", "")
                        parts.append(f"{word} {r['predicate']} {obj}")
                except Exception:
                    pass

        # QMD semantic search
        if self._http and self._qmd_url:
            try:
                resp = await self._http.post(
                    f"{self._qmd_url}/vsearch",
                    json={"query": query, "limit": 3, "collection": "workspace"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    for r in results:
                        snippet = (r.get("content", "") or "")[:200]
                        if snippet:
                            parts.append(f"[memory] {snippet}")
            except Exception:
                pass

        if not parts:
            return ""

        text = "Relevant context:\n" + "\n".join(f"- {p}" for p in parts)
        return truncate_to_tokens(text, max_tokens)

    # ------------------------------------------------------------------
    # L3: Deep Recall
    # ------------------------------------------------------------------

    async def assemble_l3(
        self,
        query: str,
        agent_name: str | None = None,
        max_tokens: int = 1000,
    ) -> str:
        """Deep search across all memory layers. ~1000 tokens. Expensive."""
        parts = []

        # Full archive search (more results)
        if self._archive:
            try:
                events = await self._archive.query(search=query, limit=10)
                for e in events:
                    data_str = e.get("data_json", "{}")
                    try:
                        data = json.loads(data_str) if isinstance(data_str, str) else data_str
                    except (json.JSONDecodeError, TypeError):
                        data = {}
                    content = data.get("content", data.get("text", data.get("msg", "")))
                    if content:
                        parts.append(f"[archive:{e['event_type']}] {str(content)[:150]}")
                    elif e.get("summary"):
                        parts.append(f"[archive:{e['event_type']}] {e['summary']}")
            except Exception:
                pass

        # KG timeline
        if self._kg:
            try:
                timeline = await self._kg.timeline(limit=10)
                for t in timeline:
                    parts.append(
                        f"[fact] {t.get('subject_name', '?')} {t['predicate']} {t.get('object_name', '?')}"
                    )
            except Exception:
                pass

        # Extended QMD search
        if self._http and self._qmd_url:
            try:
                resp = await self._http.post(
                    f"{self._qmd_url}/vsearch",
                    json={"query": query, "limit": 5, "collection": "workspace"},
                    timeout=15,
                )
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    for r in results:
                        snippet = (r.get("content", "") or "")[:300]
                        if snippet:
                            parts.append(f"[deep-memory] {snippet}")
            except Exception:
                pass

        if not parts:
            return ""

        text = "Deep recall:\n" + "\n".join(f"- {p}" for p in parts)
        return truncate_to_tokens(text, max_tokens)

    # ------------------------------------------------------------------
    # Full assembly
    # ------------------------------------------------------------------

    async def assemble(
        self,
        query: str,
        agent_name: str | None = None,
        user_name: str | None = None,
        project: str | None = None,
        system_info: dict | None = None,
        depth: str = "standard",  # "minimal" | "standard" | "deep" | "auto"
        max_total_tokens: int = 1800,
    ) -> dict:
        """Assemble the full context from all layers.

        When depth="auto", uses intent classification to determine which
        layers to prioritise and how much budget to allocate to each.

        Returns {context: str, layers: {l0, l1, l2, l3}, tokens: int, depth: str, intent: str}
        """
        t0 = time.time()
        layers = {}
        intent = "general"

        # Intent-aware depth selection
        if depth == "auto":
            from tinyagentos.intent_classifier import get_search_strategy
            strategy = get_search_strategy(query)
            intent = strategy["intent"]
            # Adjust token budgets based on intent weights
            kg_budget = int(200 * strategy["kg_weight"])
            archive_budget = int(500 * strategy["archive_weight"])
            qmd_budget = int(500 * strategy["qmd_weight"])
            depth = "deep"  # Always do deep search in auto mode, but weighted
        else:
            kg_budget = 200
            archive_budget = 500
            qmd_budget = 500

        # L0 always loaded
        layers["l0"] = await self.assemble_l0(agent_name, user_name, system_info, max_tokens=100)

        # L1 always loaded (KG facts, budget adjusted by intent)
        layers["l1"] = await self.assemble_l1(user_name, agent_name, project, max_tokens=kg_budget)

        if depth in ("standard", "deep"):
            layers["l2"] = await self.assemble_l2(query, agent_name, max_tokens=max(archive_budget, qmd_budget))
        else:
            layers["l2"] = ""

        if depth == "deep":
            layers["l3"] = await self.assemble_l3(query, agent_name, max_tokens=1000)
        else:
            layers["l3"] = ""

        # Combine and respect total budget
        sections = [v for v in layers.values() if v]
        full_context = "\n\n".join(sections)
        full_context = truncate_to_tokens(full_context, max_total_tokens)

        tokens = estimate_tokens(full_context)
        latency_ms = round((time.time() - t0) * 1000, 1)

        return {
            "context": full_context,
            "layers": {k: estimate_tokens(v) for k, v in layers.items()},
            "total_tokens": tokens,
            "depth": depth,
            "intent": intent,
            "latency_ms": latency_ms,
        }
