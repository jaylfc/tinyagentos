from __future__ import annotations
import pytest
from pathlib import Path
from tinyagentos.config import auto_register_from_manifest, AppConfig


def test_auto_register_adds_backend(tmp_path: Path):
    """auto_register_from_manifest writes a backend entry from a manifest file."""
    manifest = tmp_path / "rknn-sd.yaml"
    manifest.write_text("""
id: rknn-sd
name: RKNN Stable Diffusion
type: rknn-sd
default_url: http://localhost:7863
capabilities:
  - image-generation
lifecycle:
  auto_manage: true
  keep_alive_minutes: 10
  start_cmd: "systemctl start tinyagentos-rknn-sd"
  stop_cmd: "systemctl stop tinyagentos-rknn-sd"
  startup_timeout_seconds: 90
""")
    config = AppConfig()
    auto_register_from_manifest(manifest, config)
    assert len(config.backends) == 1
    b = config.backends[0]
    assert b["name"] == "local-rknn-sd"
    assert b["type"] == "rknn-sd"
    assert b["url"] == "http://localhost:7863"
    assert b["auto_manage"] is True
    assert b["keep_alive_minutes"] == 10


def test_auto_register_idempotent(tmp_path: Path):
    """Calling auto_register_from_manifest twice does not add duplicates."""
    manifest = tmp_path / "rknn-sd.yaml"
    manifest.write_text("""
id: rknn-sd
name: RKNN Stable Diffusion
type: rknn-sd
default_url: http://localhost:7863
lifecycle:
  auto_manage: true
  keep_alive_minutes: 10
  start_cmd: "systemctl start tinyagentos-rknn-sd"
  stop_cmd: "systemctl stop tinyagentos-rknn-sd"
  startup_timeout_seconds: 90
""")
    config = AppConfig()
    auto_register_from_manifest(manifest, config)
    auto_register_from_manifest(manifest, config)
    assert len(config.backends) == 1


def test_auto_register_catalog_manifest_format(tmp_path: Path):
    """auto_register_from_manifest works with catalog manifests that use
    type: service with lifecycle.backend_type and lifecycle.default_url."""
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("""
id: rknn-stable-diffusion
name: RKNN Stable Diffusion
type: service
lifecycle:
  backend_type: rknn-sd
  default_url: http://localhost:7863
  auto_manage: true
  keep_alive_minutes: 10
  start_cmd: "systemctl start tinyagentos-rknn-sd"
  stop_cmd: "systemctl stop tinyagentos-rknn-sd"
  startup_timeout_seconds: 90
""")
    config = AppConfig()
    auto_register_from_manifest(manifest, config)
    assert len(config.backends) == 1
    b = config.backends[0]
    assert b["type"] == "rknn-sd"
    assert b["url"] == "http://localhost:7863"
