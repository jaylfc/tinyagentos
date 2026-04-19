"""Semantic reactions for multi-agent chat.

👎 by a human on an agent-authored message → regenerate the reply.
🙋 by an agent → "wants to reply" ephemeral flag with TTL.
Everything else is purely decorative.
"""
from __future__ import annotations

import time


def _now() -> float:
    return time.monotonic()


class WantsReplyRegistry:
    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, dict[str, float]] = {}

    def add(self, channel_id: str, slug: str) -> None:
        self._entries.setdefault(channel_id, {})[slug] = _now()

    def list(self, channel_id: str) -> list[str]:
        now = _now()
        bucket = self._entries.get(channel_id) or {}
        alive = {s: t for s, t in bucket.items() if (now - t) < self._ttl}
        self._entries[channel_id] = alive
        return sorted(alive)


async def maybe_trigger_semantic(
    *, emoji: str, message: dict, reactor_id: str, reactor_type: str,
    channel: dict, state,
) -> None:
    if emoji == "👎" and reactor_type == "user" and message.get("author_type") == "agent":
        bridge = getattr(state, "bridge_sessions", None)
        if bridge is None:
            return
        await bridge.enqueue_user_message(
            message["author_id"],
            {
                "id": message.get("id"),
                "trace_id": message.get("id"),
                "channel_id": message.get("channel_id"),
                "from": reactor_id,
                "text": message.get("content", ""),
                "hops_since_user": 0,
                "force_respond": True,
                "regenerate": True,
                "context": [],
            },
        )
        return

    if emoji == "🙋" and reactor_type == "agent":
        reg = getattr(state, "wants_reply", None)
        if reg is None:
            return
        reg.add(channel["id"], reactor_id)
