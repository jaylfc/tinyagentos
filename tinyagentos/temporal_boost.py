"""Temporal Boosting for Retrieval (taOSmd).

After initial vector retrieval, reranks results by temporal alignment
with the query's temporal anchors. Improves temporal-reasoning recall
by penalising chronologically inconsistent results.

Inspired by KG-IRAG and MemoTime temporal reasoning approaches.
"""

from __future__ import annotations

import re
from datetime import datetime


# Temporal anchor patterns in queries
TEMPORAL_PATTERNS = [
    # Ordering: "first", "last", "before", "after"
    (r"\b(?:first|earliest|initially|originally)\b", "ordering_first"),
    (r"\b(?:last|latest|most recent|finally)\b", "ordering_last"),
    (r"\b(?:before|prior to|preceding)\b", "ordering_before"),
    (r"\b(?:after|following|subsequent|since)\b", "ordering_after"),
    # Duration: "how long", "how many days/weeks/months"
    (r"\bhow (?:long|many days|many weeks|many months|many years)\b", "duration"),
    # Specific time references
    (r"\b(?:yesterday|today|last week|last month|this week|this month)\b", "relative_time"),
    (r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b", "month_ref"),
    # Age/timeline
    (r"\bhow old\b", "age"),
    (r"\bwhen did\b", "when"),
]


def classify_temporal_query(query: str) -> dict:
    """Classify what kind of temporal reasoning a query requires.

    Returns {is_temporal, temporal_type, anchors}.
    """
    query_lower = query.lower()
    matches = []

    for pattern, ttype in TEMPORAL_PATTERNS:
        if re.search(pattern, query_lower):
            matches.append(ttype)

    return {
        "is_temporal": len(matches) > 0,
        "temporal_types": matches,
        "needs_ordering": any(t.startswith("ordering") for t in matches),
        "needs_duration": "duration" in matches,
        "needs_when": "when" in matches,
    }


def temporal_rerank(results: list[dict], query: str, boost_factor: float = 0.2) -> list[dict]:
    """Rerank retrieval results with temporal awareness.

    For ordering queries ("which happened first"), boosts results that contain
    temporal language matching the query's temporal anchors.

    For duration queries ("how many days"), boosts results with date/number content.
    """
    tclass = classify_temporal_query(query)

    if not tclass["is_temporal"]:
        return results  # No temporal component, return as-is

    query_lower = query.lower()

    for r in results:
        text_lower = r.get("text", "").lower()
        boost = 0.0

        # Boost results that contain temporal language
        temporal_signals = [
            r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",  # Dates
            r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d",  # Month + day
            r"\b\d{1,2}(?:st|nd|rd|th)\b",  # Ordinal dates
            r"\b(?:first|second|third|last|next|previous)\b",  # Ordinal time words
            r"\b(?:morning|afternoon|evening|night|noon)\b",  # Time of day
            r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",  # Days
            r"\b\d+\s*(?:days?|weeks?|months?|years?|hours?|minutes?)\b",  # Durations
        ]

        for pattern in temporal_signals:
            if re.search(pattern, text_lower):
                boost += boost_factor / len(temporal_signals)

        # For ordering queries, check if the text contains ordering language
        if tclass["needs_ordering"]:
            # Extract key entities from query for matching
            query_words = set(w for w in query_lower.split() if len(w) > 3)
            text_words = set(text_lower.split())
            overlap = len(query_words & text_words) / max(len(query_words), 1)
            boost += overlap * boost_factor

        # Apply boost
        if boost > 0:
            r["similarity"] = min(1.0, r.get("similarity", 0) + boost)
            r["temporal_boost"] = round(boost, 4)

    # Re-sort by boosted similarity
    results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
    return results
