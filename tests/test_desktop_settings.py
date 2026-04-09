import pytest
import pytest_asyncio
from pathlib import Path
from tinyagentos.desktop_settings import DesktopSettingsStore


@pytest_asyncio.fixture
async def store(tmp_path):
    s = DesktopSettingsStore(tmp_path / "desktop.db")
    await s.init()
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_get_default_settings(store):
    settings = await store.get_settings("user")
    assert settings["mode"] == "dark"
    assert settings["wallpaper"] == "default"
    assert "pinned" in settings["dock"]


@pytest.mark.asyncio
async def test_update_settings(store):
    await store.update_settings("user", {"mode": "light"})
    settings = await store.get_settings("user")
    assert settings["mode"] == "light"


@pytest.mark.asyncio
async def test_get_dock_layout(store):
    dock = await store.get_dock("user")
    assert isinstance(dock["pinned"], list)
    assert "messages" in dock["pinned"]


@pytest.mark.asyncio
async def test_update_dock_layout(store):
    await store.update_dock("user", {"pinned": ["agents", "files"]})
    dock = await store.get_dock("user")
    assert dock["pinned"] == ["agents", "files"]


@pytest.mark.asyncio
async def test_window_positions_roundtrip(store):
    positions = [{"appId": "messages", "x": 100, "y": 200, "w": 900, "h": 600}]
    await store.save_windows("user", positions)
    result = await store.get_windows("user")
    assert result == positions
