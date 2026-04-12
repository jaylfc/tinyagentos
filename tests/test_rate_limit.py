"""Tests for tinyagentos.rate_limit."""
from __future__ import annotations

import time

from tinyagentos.rate_limit import RateLimiter, TokenBucket, make_should_rate_limit


class TestTokenBucket:
    def test_starts_full(self):
        b = TokenBucket(capacity=5, refill_per_second=1)
        for _ in range(5):
            assert b.try_consume() is True
        assert b.try_consume() is False

    def test_refills_over_time(self, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr("time.monotonic", lambda: now[0])
        b = TokenBucket(capacity=5, refill_per_second=2)
        for _ in range(5):
            assert b.try_consume() is True
        assert b.try_consume() is False
        now[0] += 1.5  # 3 tokens should refill
        assert b.try_consume() is True
        assert b.try_consume() is True
        assert b.try_consume() is True
        assert b.try_consume() is False

    def test_capacity_cap(self, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr("time.monotonic", lambda: now[0])
        b = TokenBucket(capacity=5, refill_per_second=10)
        b.try_consume()  # 4 left
        now[0] += 100  # lots of time, but cap at 5
        assert b.try_consume() is True
        for _ in range(4):
            assert b.try_consume() is True
        assert b.try_consume() is False


class TestRateLimiter:
    def test_separate_keys(self):
        r = RateLimiter(capacity=2, refill_per_second=0)
        assert r.check("ip-a") is True
        assert r.check("ip-b") is True
        assert r.check("ip-a") is True
        assert r.check("ip-a") is False
        assert r.check("ip-b") is True
        assert r.check("ip-b") is False


class TestShouldRateLimit:
    def test_get_exempt(self):
        pred = make_should_rate_limit(["/api/agents/"])
        assert pred("GET", "/api/agents/foo") is False

    def test_post_matching_prefix(self):
        pred = make_should_rate_limit(["/api/agents/"])
        assert pred("POST", "/api/agents/foo/chat") is True

    def test_post_non_matching(self):
        pred = make_should_rate_limit(["/api/agents/"])
        assert pred("POST", "/api/cluster/workers") is False

    def test_multiple_prefixes(self):
        pred = make_should_rate_limit(["/api/agents/", "/api/cluster/route"])
        assert pred("POST", "/api/cluster/route") is True
        assert pred("POST", "/api/cluster/workers") is False
