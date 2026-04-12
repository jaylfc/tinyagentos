"""Automatic Memory Extraction (taOSmd).

Extracts structured facts from conversation text and stores them in the
Temporal Knowledge Graph. Runs after each agent conversation turn to
capture knowledge without explicit user action.

Uses lightweight keyword/pattern matching for speed (no LLM call needed).
Can optionally call an LLM for higher-quality extraction when available.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tinyagentos.temporal_knowledge_graph import TemporalKnowledgeGraph
    from tinyagentos.archive import ArchiveStore

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Pattern-based fact extraction (no LLM, runs on Pi instantly)
# ------------------------------------------------------------------

# Patterns that indicate relationships
RELATIONSHIP_PATTERNS = [
    # "X is a Y" / "X is Y"
    (r"(?:^|\. )(\w[\w\s]{1,30})\s+(?:is|are)\s+(?:a |an |the )?(\w[\w\s]{1,40}?)(?:\.|,|$)", "is_a"),
    # "X uses Y" / "X runs Y"
    (r"(?:^|\. )(\w[\w\s]{1,30})\s+(?:uses?|runs?|runs on)\s+(\w[\w\s]{1,40}?)(?:\.|,|$)", "uses"),
    # "X prefers Y" / "X likes Y"
    (r"(?:^|\. )(\w[\w\s]{1,30})\s+(?:prefers?|likes?|favou?rs?)\s+(\w[\w\s]{1,40}?)(?:\.|,|$)", "prefers"),
    # "X created Y" / "X built Y" / "X made Y"
    (r"(?:^|\. )(\w[\w\s]{1,30})\s+(?:created?|built|made|developed|wrote)\s+(\w[\w\s]{1,40}?)(?:\.|,|$)", "created"),
    # "X works on Y" / "X is working on Y"
    (r"(?:^|\. )(\w[\w\s]{1,30})\s+(?:works? on|is working on|working on)\s+(\w[\w\s]{1,40}?)(?:\.|,|$)", "works_on"),
    # "X manages Y" / "X owns Y"
    (r"(?:^|\. )(\w[\w\s]{1,30})\s+(?:manages?|owns?|maintains?)\s+(\w[\w\s]{1,40}?)(?:\.|,|$)", "manages"),
    # "X has Y" / "X includes Y"
    (r"(?:^|\. )(\w[\w\s]{1,30})\s+(?:has|have|includes?|contains?|features?)\s+(\w[\w\s]{1,40}?)(?:\.|,|$)", "has"),
    # "X supports Y"
    (r"(?:^|\. )(\w[\w\s]{1,30})\s+(?:supports?)\s+(\w[\w\s]{1,40}?)(?:\.|,|$)", "supports"),
    # "X moved to Y" / "X switched to Y"
    (r"(?:^|\. )(\w[\w\s]{1,30})\s+(?:moved? to|switched? to|migrated? to)\s+(\w[\w\s]{1,40}?)(?:\.|,|$)", "moved_to"),
    # "X depends on Y" / "X requires Y" / "X needs Y"
    (r"(?:^|\. )(\w[\w\s]{1,30})\s+(?:depends? on|requires?|needs?)\s+(\w[\w\s]{1,40}?)(?:\.|,|$)", "depends_on"),
]

# Words to skip as subjects/objects (too generic)
SKIP_WORDS = {
    "i", "we", "you", "they", "he", "she", "it", "this", "that", "these",
    "those", "the", "a", "an", "some", "all", "any", "each", "every",
    "my", "your", "our", "their", "its", "there", "here", "now", "then",
    "also", "just", "only", "very", "much", "more", "less", "most", "least",
    "really", "actually", "basically", "probably", "maybe", "perhaps",
    "something", "anything", "everything", "nothing", "someone", "anyone",
    "what", "which", "who", "whom", "where", "when", "how", "why",
}

# Minimum word length for entities
MIN_ENTITY_LEN = 2


def _clean_entity(text: str) -> str | None:
    """Clean and validate an extracted entity name."""
    text = text.strip().strip(".,;:!?\"'()[]{}").strip()
    # Skip if too short or a stop word
    if len(text) < MIN_ENTITY_LEN:
        return None
    if text.lower() in SKIP_WORDS:
        return None
    # Skip if all lowercase single word that looks like a verb/adjective
    words = text.split()
    if len(words) == 1 and text.islower() and len(text) < 4:
        return None
    return text


def extract_facts_from_text(text: str) -> list[dict]:
    """Extract structured facts from free text using pattern matching.

    Returns list of {subject, predicate, object} dicts.
    """
    facts = []
    seen = set()

    for pattern, predicate in RELATIONSHIP_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
            subject = _clean_entity(match.group(1))
            obj = _clean_entity(match.group(2))
            if not subject or not obj:
                continue
            # Deduplicate
            key = (subject.lower(), predicate, obj.lower())
            if key in seen:
                continue
            seen.add(key)
            facts.append({
                "subject": subject,
                "predicate": predicate,
                "object": obj,
            })

    return facts


# ------------------------------------------------------------------
# LLM-based extraction (higher quality, optional)
# ------------------------------------------------------------------

EXTRACTION_PROMPT = """Extract structured facts from the following text. Return a JSON array of objects, each with "subject", "predicate", and "object" fields.

Focus on:
- Relationships between named entities (people, tools, projects, hardware)
- Preferences and decisions
- Technical facts (X uses Y, X runs on Y, X supports Y)

Skip generic statements. Only extract specific, factual claims.

Text:
{text}

Return ONLY valid JSON array, no other text:"""


async def extract_facts_with_llm(
    text: str,
    llm_url: str,
    http_client,
) -> list[dict]:
    """Extract facts using an LLM for higher quality. Falls back to pattern matching."""
    if not llm_url:
        return extract_facts_from_text(text)

    try:
        resp = await http_client.post(
            f"{llm_url}/v1/chat/completions",
            json={
                "model": "default",
                "messages": [{"role": "user", "content": EXTRACTION_PROMPT.format(text=text[:2000])}],
                "temperature": 0,
                "max_tokens": 500,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            # Try to parse JSON from the response
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            facts = json.loads(content)
            if isinstance(facts, list):
                return [f for f in facts if "subject" in f and "predicate" in f and "object" in f]
    except Exception as e:
        logger.debug("LLM extraction failed, falling back to patterns: %s", e)

    return extract_facts_from_text(text)


# ------------------------------------------------------------------
# Auto-extraction pipeline
# ------------------------------------------------------------------

async def process_conversation_turn(
    text: str,
    agent_name: str | None,
    kg: TemporalKnowledgeGraph,
    archive: ArchiveStore | None = None,
    source: str = "conversation",
) -> list[str]:
    """Extract facts from a conversation turn and store in the KG.

    Returns list of triple IDs that were created.
    """
    facts = extract_facts_from_text(text)
    triple_ids = []

    for fact in facts:
        try:
            tid = await kg.add_triple(
                subject=fact["subject"],
                predicate=fact["predicate"],
                obj=fact["object"],
                source=f"{source}:{agent_name or 'user'}",
            )
            triple_ids.append(tid)
        except Exception as e:
            logger.debug("Failed to add triple: %s", e)

    # Archive the extraction event
    if archive and triple_ids:
        await archive.record(
            event_type="memory_extraction",
            data={
                "facts_extracted": len(facts),
                "triples_created": len(triple_ids),
                "source": source,
                "facts": facts,
            },
            agent_name=agent_name,
            summary=f"Extracted {len(facts)} facts from {source}",
        )

    return triple_ids
