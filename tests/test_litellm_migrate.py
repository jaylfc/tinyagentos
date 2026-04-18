"""Tests for litellm_migrate — idempotent Prisma schema bootstrap."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tinyagentos import litellm_migrate


def _write_db_url(tmp_path: Path, url: str = "postgresql://u:p@h/db") -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / ".litellm_db_url").write_text(url)
    return data_dir


def test_no_db_url_returns_no_db(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # No .litellm_db_url file — should no-op even with no other setup.
    assert litellm_migrate.migrate(data_dir) == "no-db"


def test_empty_db_url_returns_no_db(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / ".litellm_db_url").write_text("   \n")
    assert litellm_migrate.migrate(data_dir) == "no-db"


def test_schema_already_applied_no_subprocess(tmp_path):
    """When the probe table exists, migrate() must skip prisma calls."""
    data_dir = _write_db_url(tmp_path)
    fake_schema = tmp_path / "schema.prisma"
    fake_schema.write_text("// fake")

    with patch.object(litellm_migrate, "_schema_path", return_value=fake_schema), \
         patch.object(litellm_migrate, "_schema_already_applied", return_value=True), \
         patch.object(litellm_migrate, "_run") as run_mock:
        assert litellm_migrate.migrate(data_dir) == "already-applied"
        run_mock.assert_not_called()


def test_missing_tables_triggers_generate_and_push(tmp_path):
    """When the probe table is absent, migrate() must shell out."""
    data_dir = _write_db_url(tmp_path)
    fake_schema = tmp_path / "schema.prisma"
    fake_schema.write_text("// fake")
    fake_cli = tmp_path / "prisma"
    fake_cli.write_text("#!/bin/sh\nexit 0\n")
    fake_cli.chmod(0o755)

    # First probe call → False (not applied), second probe (post-migrate) → True.
    probe_results = iter([False, True])

    with patch.object(litellm_migrate, "_schema_path", return_value=fake_schema), \
         patch.object(litellm_migrate, "_schema_already_applied",
                      side_effect=lambda _url: next(probe_results)), \
         patch.object(litellm_migrate, "_prisma_cli", return_value=str(fake_cli)), \
         patch.object(litellm_migrate, "_run") as run_mock:
        assert litellm_migrate.migrate(data_dir) == "applied"

    # Expect two calls: `prisma generate --schema=...` then
    # `prisma db push --accept-data-loss --schema=...`.
    assert run_mock.call_count == 2
    gen_cmd = run_mock.call_args_list[0][0][0]
    push_cmd = run_mock.call_args_list[1][0][0]
    assert gen_cmd[:2] == [str(fake_cli), "generate"]
    assert any(a.startswith("--schema=") for a in gen_cmd)
    assert push_cmd[:3] == [str(fake_cli), "db", "push"]
    assert "--accept-data-loss" in push_cmd
    # DATABASE_URL must be exported in the subprocess env.
    gen_env = run_mock.call_args_list[0][0][1]
    push_env = run_mock.call_args_list[1][0][1]
    assert gen_env["DATABASE_URL"] == "postgresql://u:p@h/db"
    assert push_env["DATABASE_URL"] == "postgresql://u:p@h/db"


def test_generate_env_prepends_venv_bin_to_path(tmp_path, monkeypatch):
    """Prisma's node CLI shells out to ``prisma-client-py`` during generate;
    under systemd the PATH default doesn't include the venv's bin/. We must
    prepend the prisma CLI's bin directory to PATH so the child shell can
    resolve ``prisma-client-py`` without a global install."""
    data_dir = _write_db_url(tmp_path)
    fake_schema = tmp_path / "schema.prisma"
    fake_schema.write_text("// fake")
    fake_cli = tmp_path / "fake-venv" / "bin" / "prisma"
    fake_cli.parent.mkdir(parents=True)
    fake_cli.write_text("#!/bin/sh\nexit 0\n")
    fake_cli.chmod(0o755)

    # Seed a PATH that omits the venv's bin — simulates systemd's default.
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    probe_results = iter([False, True])
    with patch.object(litellm_migrate, "_schema_path", return_value=fake_schema), \
         patch.object(litellm_migrate, "_schema_already_applied",
                      side_effect=lambda _url: next(probe_results)), \
         patch.object(litellm_migrate, "_prisma_cli", return_value=str(fake_cli)), \
         patch.object(litellm_migrate, "_run") as run_mock:
        litellm_migrate.migrate(data_dir)

    gen_env = run_mock.call_args_list[0][0][1]
    venv_bin = str(fake_cli.parent)
    # The venv bin must appear at the front, ahead of the ambient PATH.
    assert gen_env["PATH"].startswith(venv_bin + ":"), gen_env["PATH"]


def test_nonzero_exit_raises(tmp_path):
    """A failing prisma subprocess must raise so taOS boot surfaces it."""
    data_dir = _write_db_url(tmp_path)
    fake_schema = tmp_path / "schema.prisma"
    fake_schema.write_text("// fake")
    fake_cli = tmp_path / "prisma"
    fake_cli.write_text("#!/bin/sh\nexit 1\n")
    fake_cli.chmod(0o755)

    # Use the real _run so we get the real non-zero handling.
    with patch.object(litellm_migrate, "_schema_path", return_value=fake_schema), \
         patch.object(litellm_migrate, "_schema_already_applied", return_value=False), \
         patch.object(litellm_migrate, "_prisma_cli", return_value=str(fake_cli)):
        with pytest.raises(RuntimeError, match="exited 1"):
            litellm_migrate.migrate(data_dir)


def test_missing_cli_raises(tmp_path):
    data_dir = _write_db_url(tmp_path)
    fake_schema = tmp_path / "schema.prisma"
    fake_schema.write_text("// fake")

    with patch.object(litellm_migrate, "_schema_path", return_value=fake_schema), \
         patch.object(litellm_migrate, "_schema_already_applied", return_value=False), \
         patch.object(litellm_migrate, "_prisma_cli",
                      return_value=str(tmp_path / "does-not-exist")):
        with pytest.raises(RuntimeError, match="prisma CLI not found"):
            litellm_migrate.migrate(data_dir)


def test_post_migration_probe_still_missing_raises(tmp_path):
    """If the probe still fails after generate+push, raise — don't lie."""
    data_dir = _write_db_url(tmp_path)
    fake_schema = tmp_path / "schema.prisma"
    fake_schema.write_text("// fake")
    fake_cli = tmp_path / "prisma"
    fake_cli.write_text("#!/bin/sh\nexit 0\n")
    fake_cli.chmod(0o755)

    with patch.object(litellm_migrate, "_schema_path", return_value=fake_schema), \
         patch.object(litellm_migrate, "_schema_already_applied", return_value=False), \
         patch.object(litellm_migrate, "_prisma_cli", return_value=str(fake_cli)), \
         patch.object(litellm_migrate, "_run"):
        with pytest.raises(RuntimeError, match="probe table still missing"):
            litellm_migrate.migrate(data_dir)


def test_missing_schema_returns_status(tmp_path):
    """If litellm isn't installed / schema.prisma missing, short-circuit."""
    data_dir = _write_db_url(tmp_path)
    with patch.object(litellm_migrate, "_schema_path", return_value=None):
        assert litellm_migrate.migrate(data_dir) == "no-schema"


def test_run_propagates_stdout_and_stderr(tmp_path, caplog):
    """_run must log stdout/stderr and succeed on exit 0."""
    import logging
    caplog.set_level(logging.INFO, logger="tinyagentos.litellm_migrate")
    script = tmp_path / "echo.sh"
    script.write_text("#!/bin/sh\necho hello-stdout\necho hello-stderr >&2\nexit 0\n")
    script.chmod(0o755)
    litellm_migrate._run([str(script)], env={})
    assert any("hello-stdout" in r.message for r in caplog.records)
    assert any("hello-stderr" in r.message for r in caplog.records)
