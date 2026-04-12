"""Simple in-process token-bucket rate limiter for controller endpoints.

This is a defence-in-depth knob, not a full DDoS shield. It exists so
that a runaway agent loop, a misconfigured MCP client, or an accidental
infinite retry cannot hammer the controller into exhaustion. The bucket
is keyed on the calling client's IP address and refilled at a steady
rate; bursts up to the capacity are allowed, then requests over the
rate get a ``429 Too Many Requests``.

The controller wires this in as a FastAPI middleware for mutating
endpoints only — read-only GETs (health, cluster list, dashboards) are
exempt so a UI refresh storm does not start 429-ing. The bucket state
is in-process; a restart resets everything, which is the right trade-off
for a self-hosted single-process controller.

Users who need cross-process or cross-host rate limiting should front
the controller with Caddy or nginx and use their built-in limiters.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class TokenBucket:
    """A classic token bucket.

    ``capacity`` is the maximum burst size. ``refill_per_second`` is
    the steady-state rate. ``tokens`` is the current fill; when a
    request arrives we refill based on elapsed time, then try to
    consume one token.
    """

    capacity: float
    refill_per_second: float
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = float(self.capacity)
        self.last_refill = time.monotonic()

    def try_consume(self, cost: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.last_refill = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False


class RateLimiter:
    """Per-key bucket registry.

    The key is typically the client IP, but the caller picks whatever
    granularity it wants. A dedicated key per authenticated user, a
    shared key for all anonymous traffic, whatever.
    """

    def __init__(self, capacity: float = 30, refill_per_second: float = 10.0):
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self._buckets: dict[str, TokenBucket] = {}

    def check(self, key: str, cost: float = 1.0) -> bool:
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(self.capacity, self.refill_per_second)
            self._buckets[key] = bucket
        return bucket.try_consume(cost)


def make_should_rate_limit(paths_to_limit: list[str]) -> Callable[[str, str], bool]:
    """Build a path-matching predicate.

    ``paths_to_limit`` is a list of path prefixes that *should* be rate
    limited. Returns a callable ``(method, path) -> bool`` that answers
    "should this request be gated on the limiter?" The controller's
    middleware calls it to decide whether to check the bucket at all.
    GET requests are always exempt, since reading controller state is
    cheap and a UI refresh loop should not be penalised.
    """

    def should(method: str, path: str) -> bool:
        if method.upper() == "GET":
            return False
        return any(path.startswith(p) for p in paths_to_limit)

    return should
