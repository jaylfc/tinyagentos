"""Preference Extraction (taOSmd).

Detects implicit preference signals in conversation text and generates
synthetic preference documents for better retrieval. Based on MemPalace's
approach of bridging the vocabulary gap between how preferences are stated
("I find Postgres more reliable") and how they're queried ("What database
does the user prefer?").
"""

from __future__ import annotations

import re

# Patterns that signal implicit preferences
PREFERENCE_PATTERNS = [
    # Direct preferences
    (r"(?:I|we)\s+(?:prefer|like|love|enjoy|favour)\s+(.+?)(?:\.|,|$)", "positive"),
    (r"(?:I|we)\s+(?:don't like|dislike|hate|avoid|can't stand)\s+(.+?)(?:\.|,|$)", "negative"),
    # Comparatives
    (r"(\w[\w\s]+?)\s+(?:is|are)\s+(?:better|nicer|faster|easier|more reliable|more intuitive)\s+(?:than\s+)?(.+?)(?:\.|,|$)", "comparative"),
    (r"(?:I|we)\s+(?:find|think)\s+(\w[\w\s]+?)\s+(?:better|more|easier|faster|nicer)\s+(?:than\s+)?(.+?)(?:\.|,|$)", "comparative"),
    # Habitual choices
    (r"(?:I|we)\s+(?:always|usually|typically|tend to|mostly)\s+(?:use|go with|pick|choose|opt for)\s+(.+?)(?:\.|,|$)", "habitual"),
    (r"(?:I|we)\s+(?:never|rarely|seldom)\s+(?:use|go with|pick|choose)\s+(.+?)(?:\.|,|$)", "avoidance"),
    # Hedged endorsements
    (r"(?:I|we)\s+(?:find|think)\s+(\w[\w\s]+?)\s+(?:really |very |quite )?(?:reliable|useful|helpful|great|solid|good|excellent|fast|intuitive|clean)(?:\s|\.|\,|$)", "endorsement"),
    # Recommendations received
    (r"(?:I|we)\s+(?:was|were)\s+(?:recommended|suggested|told to use|advised to try)\s+(.+?)(?:\.|,|$)", "recommendation"),
    # Settings/configurations
    (r"(?:I|we)\s+(?:set|configure|use|keep)\s+(?:my|our|the)\s+(.+?)\s+(?:to|at|as)\s+(.+?)(?:\.|,|$)", "setting"),
    # "X over Y" pattern
    (r"(\w[\w\s]+?)\s+over\s+(\w[\w\s]+?)(?:\.|,|$)", "over"),
    # "rather X than Y"
    (r"(?:rather|instead of)\s+(\w[\w\s]+?)\s+(?:than|instead)\s+(\w[\w\s]+?)(?:\.|,|$)", "rather"),
]


def extract_preferences(text: str) -> list[dict]:
    """Extract implicit preferences from text.

    Returns list of {signal, valence, text, synthetic_doc}.
    """
    preferences = []
    seen = set()

    for pattern, valence in PREFERENCE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            signal = match.group(0).strip().rstrip(".,")
            if signal.lower() in seen or len(signal) < 5:
                continue
            seen.add(signal.lower())

            # Generate synthetic preference document
            if valence == "comparative" and match.lastindex >= 2:
                preferred = match.group(1).strip()
                over = match.group(2).strip()
                synthetic = f"User preference: prefers {preferred} over {over}."
            elif valence == "negative":
                thing = match.group(1).strip()
                synthetic = f"User preference: dislikes or avoids {thing}."
            elif valence == "avoidance":
                thing = match.group(1).strip()
                synthetic = f"User preference: rarely or never uses {thing}."
            elif valence == "setting" and match.lastindex >= 2:
                what = match.group(1).strip()
                value = match.group(2).strip()
                synthetic = f"User preference: configures {what} to {value}."
            elif valence == "over" and match.lastindex >= 2:
                preferred = match.group(1).strip()
                over = match.group(2).strip()
                synthetic = f"User preference: prefers {preferred} over {over}."
            elif valence == "rather" and match.lastindex >= 2:
                preferred = match.group(1).strip()
                over = match.group(2).strip()
                synthetic = f"User preference: prefers {preferred} over {over}."
            else:
                thing = match.group(1).strip() if match.lastindex >= 1 else signal
                synthetic = f"User preference: {thing}."

            preferences.append({
                "signal": signal,
                "valence": valence,
                "text": text[:200],
                "synthetic_doc": synthetic,
            })

    return preferences


def generate_synthetic_preference_docs(text: str) -> list[str]:
    """Generate synthetic preference documents for vector indexing.

    These bridge the vocabulary gap between how preferences are stated
    and how they're queried.
    """
    prefs = extract_preferences(text)
    return [p["synthetic_doc"] for p in prefs]
