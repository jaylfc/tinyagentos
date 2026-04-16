import os
import stat
from pathlib import Path

import pytest

from tinyagentos.agent_env import (
    env_file_path,
    read_env_file,
    update_agent_env_file,
)


class TestAgentEnvFile:
    def test_read_missing_file_returns_empty(self, tmp_path):
        assert read_env_file(tmp_path) == {}

    def test_write_new_file_and_read_back(self, tmp_path):
        path = update_agent_env_file(
            tmp_path,
            {"OPENAI_API_KEY": "sk-abc", "TAOS_MODEL": "claude-3.5"},
        )
        assert path == env_file_path(tmp_path)
        assert path.exists()
        parsed = read_env_file(tmp_path)
        assert parsed == {"OPENAI_API_KEY": "sk-abc", "TAOS_MODEL": "claude-3.5"}

    def test_permissions_are_0600_and_0700_dir(self, tmp_path):
        update_agent_env_file(tmp_path, {"K": "v"})
        path = env_file_path(tmp_path)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700

    def test_merge_preserves_untouched_keys(self, tmp_path):
        update_agent_env_file(tmp_path, {"A": "1", "B": "2", "C": "3"})
        update_agent_env_file(tmp_path, {"B": "new"})
        assert read_env_file(tmp_path) == {"A": "1", "B": "new", "C": "3"}

    def test_none_value_removes_key(self, tmp_path):
        update_agent_env_file(tmp_path, {"A": "1", "B": "2"})
        update_agent_env_file(tmp_path, {"A": None})
        assert read_env_file(tmp_path) == {"B": "2"}

    def test_create_if_missing_false_raises_when_absent(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            update_agent_env_file(tmp_path, {"A": "1"}, create_if_missing=False)

    def test_atomic_write_leaves_no_temp_on_success(self, tmp_path):
        update_agent_env_file(tmp_path, {"A": "1"})
        temps = [p for p in (tmp_path / ".openclaw").iterdir() if p.name.startswith(".env-")]
        assert temps == []

    def test_ignores_comments_and_blanks(self, tmp_path):
        # Seed a file with comments + blanks
        d = tmp_path / ".openclaw"
        d.mkdir(mode=0o700)
        (d / "env").write_text("# header\n\nA=1\n  # indented comment ignored\nB=2\n")
        os.chmod(d / "env", 0o600)
        assert read_env_file(tmp_path) == {"A": "1", "B": "2"}
