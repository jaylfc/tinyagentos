"""Rolling context-window builder for per-bridge chat context.

Takes a list of channel messages (oldest-first) and returns a trimmed window
respecting both a message count limit and a token budget. Drops oldest
messages first when trimming. System messages (slash-command echoes) are
excluded entirely.
"""
from __future__ import annotations


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def build_context_window(messages: list[dict], *, limit: int, max_tokens: int) -> list[dict]:
    eligible = [m for m in messages if m.get("author_type") != "system"]
    if len(eligible) > limit:
        eligible = eligible[-limit:]
    while eligible and sum(estimate_tokens(m.get("content", "")) for m in eligible) > max_tokens:
        eligible = eligible[1:]
    return [
        {
            "author_id": m.get("author_id"),
            "author_type": m.get("author_type"),
            "content": m.get("content") or "",
        }
        for m in eligible
    ]
