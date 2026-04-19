import pytest
import time
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_prune_old_snapshots_keeps_three_newest():
    from tinyagentos.framework_update import _prune_old_snapshots
    snaps = [
        {"name": f"pre-framework-update-{i}", "created_at": f"2026/04/18 {22-i}:00 UTC"}
        for i in range(5)
    ]  # newest first
    deleted = []
    with patch("tinyagentos.framework_update.snapshot_list",
               new=AsyncMock(return_value=snaps)), \
         patch("tinyagentos.framework_update.snapshot_delete",
               new=AsyncMock(side_effect=lambda _c, n: deleted.append(n))):
        await _prune_old_snapshots("taos-agent-atlas", keep=3)
    assert deleted == ["pre-framework-update-3", "pre-framework-update-4"]


@pytest.mark.asyncio
async def test_prune_noop_when_under_limit():
    from tinyagentos.framework_update import _prune_old_snapshots
    with patch("tinyagentos.framework_update.snapshot_list",
               new=AsyncMock(return_value=[{"name": "x", "created_at": ""}])), \
         patch("tinyagentos.framework_update.snapshot_delete",
               new=AsyncMock()) as d:
        await _prune_old_snapshots("taos-agent-atlas", keep=3)
    d.assert_not_awaited()
