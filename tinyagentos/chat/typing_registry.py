"""In-memory per-channel typing / thinking heartbeat tracker.

Humans refresh via keystroke-debounced POSTs; agent bridges fire
start/end around their LLM call. Stale entries auto-clear after a
per-kind TTL. Single-process, matches the rest of the chat infra.
"""
from __future__ import annotations

import time
from typing import Literal


def _now() -> float:
    return time.monotonic()


Kind = Literal["human", "agent"]


class TypingRegistry:
    def __init__(self, human_ttl: int = 3, agent_ttl: int = 45) -> None:
        self._ttls: dict[str, int] = {"human": human_ttl, "agent": agent_ttl}
        # (channel_id, slug) -> (kind, expires_at)
        self._entries: dict[tuple[str, str], tuple[Kind, float]] = {}

    def mark(self, channel_id: str, slug: str, kind: Kind) -> None:
        now = _now()
        ttl = self._ttls[kind]
        self._entries[(channel_id, slug)] = (kind, now + ttl)

    def clear(self, channel_id: str, slug: str) -> None:
        self._entries.pop((channel_id, slug), None)

    def list(self, channel_id: str) -> dict[str, list[str]]:
        now = _now()
        out: dict[str, list[str]] = {"human": [], "agent": []}
        stale: list[tuple[str, str]] = []
        for (ch, slug), (kind, expires_at) in self._entries.items():
            if ch != channel_id:
                continue
            if expires_at < now:
                stale.append((ch, slug))
                continue
            out[kind].append(slug)
        for k in stale:
            self._entries.pop(k, None)
        out["human"].sort()
        out["agent"].sort()
        return out
