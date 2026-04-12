"""Intent-Aware Retrieval Planning (taOSmd).

Inspired by SimpleMem's Intent-Aware Retrieval Planning.
Classifies query intent to determine which memory layers to search
and in what order, instead of searching everything blindly.

This is a lightweight, no-LLM classifier — runs in microseconds.
"""

from __future__ import annotations

import re

# Intent types
INTENT_FACTUAL = "factual"         # "What X is Y?", "Who created Z?"
INTENT_RECENT = "recent"           # "What happened yesterday?", "Latest updates?"
INTENT_PREFERENCE = "preference"   # "What does Jay prefer?", "How do I usually..."
INTENT_TECHNICAL = "technical"     # "How does X work?", "Explain the architecture"
INTENT_EXPLORATORY = "exploratory" # "Tell me about X", "Find anything about Y"
INTENT_RELATIONAL = "relational"   # "What does X depend on?", "Who manages Y?"

# Search strategies per intent
SEARCH_STRATEGIES = {
    INTENT_FACTUAL: {
        "primary": "kg",        # Search KG first — structured facts
        "secondary": "archive", # Then archive for context
        "tertiary": "qmd",     # QMD last
        "kg_weight": 1.0,
        "archive_weight": 0.3,
        "qmd_weight": 0.2,
    },
    INTENT_RECENT: {
        "primary": "archive",   # Search archive first — recent events
        "secondary": "kg",
        "tertiary": "qmd",
        "kg_weight": 0.3,
        "archive_weight": 1.0,
        "qmd_weight": 0.2,
    },
    INTENT_PREFERENCE: {
        "primary": "kg",        # Preferences are structured in KG
        "secondary": "archive",
        "tertiary": "qmd",
        "kg_weight": 1.0,
        "archive_weight": 0.5,
        "qmd_weight": 0.1,
    },
    INTENT_TECHNICAL: {
        "primary": "qmd",       # Technical docs are in vector store
        "secondary": "kg",
        "tertiary": "archive",
        "kg_weight": 0.5,
        "archive_weight": 0.3,
        "qmd_weight": 1.0,
    },
    INTENT_EXPLORATORY: {
        "primary": "qmd",       # Broad search needs semantic matching
        "secondary": "kg",
        "tertiary": "archive",
        "kg_weight": 0.7,
        "archive_weight": 0.5,
        "qmd_weight": 1.0,
    },
    INTENT_RELATIONAL: {
        "primary": "kg",        # Relationships are in the KG
        "secondary": "archive",
        "tertiary": "qmd",
        "kg_weight": 1.0,
        "archive_weight": 0.2,
        "qmd_weight": 0.1,
    },
}

# Keyword patterns for intent classification
INTENT_PATTERNS = {
    INTENT_FACTUAL: [
        r"\bwhat (?:is|are|was|were)\b",
        r"\bwho (?:is|are|was|created|made|built)\b",
        r"\bwhere (?:is|are|does)\b",
        r"\bhow many\b",
        r"\bwhich\b.*\buse",
        r"\bwhat.*\brun(?:s|ning)? on\b",
        r"\bwhat.*\bname",
        r"\bwhat.*\bcalled\b",
    ],
    INTENT_RECENT: [
        r"\brecent(?:ly)?\b",
        r"\blast (?:time|week|month|day|session)\b",
        r"\byesterday\b",
        r"\btoday\b",
        r"\bjust (?:now|happened)\b",
        r"\blatest\b",
        r"\bwhat happened\b",
        r"\bwhat changed\b",
        r"\bnew\b.*\b(?:update|change|event)\b",
    ],
    INTENT_PREFERENCE: [
        r"\bprefer(?:s|red|ence)?\b",
        r"\bfavou?rite\b",
        r"\busually\b",
        r"\balways\b",
        r"\bdefault\b",
        r"\blike(?:s)? to\b",
        r"\brather\b",
    ],
    INTENT_TECHNICAL: [
        r"\bhow does\b",
        r"\bhow do(?:es)?\b.*\bwork\b",
        r"\bexplain\b",
        r"\barchitecture\b",
        r"\bimplement(?:ation|ed)?\b",
        r"\btechnical\b",
        r"\bunder the hood\b",
        r"\bdesign\b",
        r"\bpipeline\b",
    ],
    INTENT_RELATIONAL: [
        r"\bdepend(?:s|ing)? on\b",
        r"\bmanage(?:s|d)?\b",
        r"\bmonitor(?:s|ing)?\b",
        r"\bconnect(?:s|ed)? to\b",
        r"\brelat(?:ed|ionship)\b",
        r"\bwho (?:manages|owns|runs)\b",
        r"\bwhat.*\buse(?:s|d)?\b",
    ],
}


def classify_intent(query: str) -> str:
    """Classify a query's intent for optimal retrieval strategy.

    Returns one of: factual, recent, preference, technical, exploratory, relational.
    """
    query_lower = query.lower().strip()

    # Score each intent
    scores: dict[str, int] = {intent: 0 for intent in INTENT_PATTERNS}

    # Temporal/recency signals get a 2x boost since they're highly specific
    boost = {INTENT_RECENT: 2, INTENT_PREFERENCE: 2}
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, query_lower):
                scores[intent] += boost.get(intent, 1)

    # Find best match
    best_intent = max(scores, key=scores.get)
    if scores[best_intent] > 0:
        return best_intent

    # Default to exploratory if no patterns match
    return INTENT_EXPLORATORY


def get_search_strategy(query: str) -> dict:
    """Get the optimal search strategy for a query.

    Returns {intent, primary, secondary, tertiary, weights}.
    """
    intent = classify_intent(query)
    strategy = SEARCH_STRATEGIES[intent]
    return {
        "intent": intent,
        **strategy,
    }
