import pytest
from unittest.mock import patch
from tinyagentos.containers.backend import detect_runtime


class TestDetectRuntime:
    def test_detect_lxc(self):
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/incus" if x == "incus" else None):
            assert detect_runtime() == "lxc"

    def test_detect_docker(self):
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/docker" if x == "docker" else None):
            assert detect_runtime() == "docker"

    def test_detect_podman(self):
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/podman" if x == "podman" else None):
            assert detect_runtime() == "podman"

    def test_detect_none(self):
        with patch("shutil.which", return_value=None):
            assert detect_runtime() == "none"

    def test_prefers_lxc_over_docker(self):
        def which(cmd):
            if cmd in ("incus", "docker"):
                return f"/usr/bin/{cmd}"
            return None
        with patch("shutil.which", side_effect=which):
            assert detect_runtime() == "lxc"
