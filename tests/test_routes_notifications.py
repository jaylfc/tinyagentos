import pytest
from tinyagentos.notifications import NotificationStore


class TestNotificationStore:
    @pytest.mark.asyncio
    async def test_emit_event_stores_notification(self, tmp_path):
        store = NotificationStore(tmp_path / "notif.db")
        await store.init()
        try:
            await store.emit_event("worker.join", "Worker joined", "worker-1 connected", level="info")
            items = await store.list(limit=10)
            assert len(items) == 1
            assert items[0]["title"] == "Worker joined"
            assert items[0]["source"] == "worker.join"
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_emit_event_respects_muted_prefs(self, tmp_path):
        store = NotificationStore(tmp_path / "notif.db")
        await store.init()
        try:
            await store.set_event_muted("worker.join", True)
            await store.emit_event("worker.join", "Worker joined", "worker-1 connected")
            items = await store.list(limit=10)
            assert len(items) == 0
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_get_event_prefs(self, tmp_path):
        store = NotificationStore(tmp_path / "notif.db")
        await store.init()
        try:
            prefs = await store.get_event_prefs()
            assert isinstance(prefs, list)
            await store.set_event_muted("backend.down", True)
            prefs = await store.get_event_prefs()
            muted = [p for p in prefs if p["event_type"] == "backend.down"]
            assert len(muted) == 1
            assert muted[0]["muted"] is True
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_emit_unmuted_event_passes_through(self, tmp_path):
        store = NotificationStore(tmp_path / "notif.db")
        await store.init()
        try:
            await store.set_event_muted("worker.join", True)
            await store.emit_event("backend.up", "Backend online", "test-backend connected")
            items = await store.list(limit=10)
            assert len(items) == 1
            assert items[0]["title"] == "Backend online"
        finally:
            await store.close()
