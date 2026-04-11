"""Tests for WorkerInfo KV cache quant plumbing."""
from __future__ import annotations

from dataclasses import asdict

import pytest

from tinyagentos.cluster.worker_protocol import WorkerInfo
from tinyagentos.cluster.manager import ClusterManager


# ---------------------------------------------------------------------------
# WorkerInfo field defaults
# ---------------------------------------------------------------------------

class TestWorkerInfoKvQuantDefault:
    def test_default_is_fp16_only(self):
        w = WorkerInfo(name="w", url="http://localhost:9000")
        assert w.kv_cache_quant_support == ["fp16"]

    def test_custom_value_stored(self):
        w = WorkerInfo(
            name="w",
            url="http://localhost:9000",
            kv_cache_quant_support=["fp16", "turboquant-k3v2"],
        )
        assert w.kv_cache_quant_support == ["fp16", "turboquant-k3v2"]

    def test_serialises_via_asdict(self):
        w = WorkerInfo(
            name="w",
            url="http://localhost:9000",
            kv_cache_quant_support=["fp16", "int4-kv"],
        )
        d = asdict(w)
        assert "kv_cache_quant_support" in d
        assert d["kv_cache_quant_support"] == ["fp16", "int4-kv"]

    def test_roundtrip_default(self):
        w = WorkerInfo(name="w", url="http://localhost:9000")
        d = asdict(w)
        # Reconstruct from the serialised form; kv_cache_quant_support must
        # survive the round-trip.
        w2 = WorkerInfo(**{k: v for k, v in d.items()})
        assert w2.kv_cache_quant_support == ["fp16"]

    def test_roundtrip_custom(self):
        original = ["fp16", "turboquant-k3v2"]
        w = WorkerInfo(
            name="w",
            url="http://localhost:9000",
            kv_cache_quant_support=original,
        )
        d = asdict(w)
        w2 = WorkerInfo(**{k: v for k, v in d.items()})
        assert w2.kv_cache_quant_support == original


# ---------------------------------------------------------------------------
# ClusterManager.kv_quant_union
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestKvQuantUnion:
    async def _register(self, mgr: ClusterManager, name: str, quant: list[str]) -> None:
        w = WorkerInfo(
            name=name,
            url=f"http://localhost:900{name[-1]}",
            kv_cache_quant_support=quant,
        )
        await mgr.register_worker(w)

    async def test_empty_cluster_returns_fp16(self):
        mgr = ClusterManager()
        assert mgr.kv_quant_union() == ["fp16"]

    async def test_all_fp16_cluster_returns_fp16(self):
        mgr = ClusterManager()
        await self._register(mgr, "w1", ["fp16"])
        await self._register(mgr, "w2", ["fp16"])
        assert mgr.kv_quant_union() == ["fp16"]

    async def test_mixed_cluster_returns_union(self):
        mgr = ClusterManager()
        await self._register(mgr, "w1", ["fp16"])
        await self._register(mgr, "w2", ["fp16", "turboquant-k3v2"])
        result = mgr.kv_quant_union()
        assert "fp16" in result
        assert "turboquant-k3v2" in result
        assert len(result) == 2

    async def test_offline_worker_excluded(self):
        mgr = ClusterManager()
        await self._register(mgr, "w1", ["fp16", "turboquant-k3v2"])
        # Mark it offline
        mgr._workers["w1"].status = "offline"
        # Without an online worker only the baseline fp16 is returned.
        assert mgr.kv_quant_union() == ["fp16"]

    async def test_result_is_sorted(self):
        mgr = ClusterManager()
        await self._register(mgr, "w1", ["turboquant-k3v2", "fp16"])
        result = mgr.kv_quant_union()
        assert result == sorted(result)

    async def test_fp16_always_present(self):
        """fp16 is the baseline — always in the union even if no worker lists it."""
        mgr = ClusterManager()
        # Simulate a hypothetical backend that only lists a new type.
        await self._register(mgr, "w1", ["turboquant-k3v2"])
        result = mgr.kv_quant_union()
        assert "fp16" in result

    async def test_heartbeat_updates_kv_quant(self):
        mgr = ClusterManager()
        await self._register(mgr, "w1", ["fp16"])
        assert mgr.kv_quant_union() == ["fp16"]

        # Worker sends an updated heartbeat (e.g. after a backend upgrade).
        mgr.heartbeat("w1", kv_cache_quant_support=["fp16", "turboquant-k3v2"])
        result = mgr.kv_quant_union()
        assert "turboquant-k3v2" in result
