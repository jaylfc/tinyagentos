"""Host-side helper for rewriting the per-agent env file bind-mounted
into the container as /root/.openclaw/env.

The container's openclaw runtime (and any future framework that follows
the same convention) reads this file as a systemd ``EnvironmentFile=``.
Re-running install.sh on every env change is heavy and risks breaking
the framework install, so this module offers a surgical edit path:
read -> merge -> atomic write, preserving unknown keys.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Path relative to the agent's home mount. If the on-container path
# ever moves, change this constant. Callers pass the host-side
# agent_home directory (``data_dir/agent-home/<slug>``) -- they don't
# need to know the subpath.
ENV_FILE_REL = Path(".openclaw/env")


def env_file_path(agent_home: Path) -> Path:
    """Return the absolute path to the env file for a given agent home dir."""
    return agent_home / ENV_FILE_REL


def read_env_file(agent_home: Path) -> dict[str, str]:
    """Parse the current env file. Returns an empty dict if the file
    doesn't exist yet -- callers can treat that as 'nothing to merge into,
    start fresh'.

    Parses only ``KEY=VALUE`` lines (systemd EnvironmentFile syntax:
    no shell expansion, no quoting, no multiline). Comments (lines
    starting with ``#``) and blank lines are ignored.
    """
    path = env_file_path(agent_home)
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        result[k.strip()] = v
    return result


def update_agent_env_file(
    agent_home: Path,
    updates: dict[str, str | None],
    *,
    create_if_missing: bool = True,
) -> Path:
    """Merge ``updates`` into the agent's env file and write atomically.

    A value of ``None`` in ``updates`` removes that key. Missing files
    are created iff ``create_if_missing`` is True (the default) -- this
    supports both the restore path (file exists from install.sh) and
    future host-first flows where the host owns env from day one.

    The write is via ``tempfile + os.replace`` so partial failures
    never produce a half-written file; permissions are set to 0o600 on
    the final file. The parent ``.openclaw/`` directory is created
    with 0o700 if missing.

    Returns the path of the written file.
    """
    path = env_file_path(agent_home)
    existing = read_env_file(agent_home)

    if not existing and not create_if_missing:
        raise FileNotFoundError(f"env file missing: {path}")

    # Apply updates (None removes).
    for key, val in updates.items():
        if val is None:
            existing.pop(key, None)
        else:
            existing[key] = val

    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Respect an existing parent mode if it's stricter, but ensure
    # ours is never looser than 0o700.
    try:
        current_mode = path.parent.stat().st_mode & 0o777
        if current_mode & 0o077:
            os.chmod(path.parent, 0o700)
    except FileNotFoundError:
        pass

    # Deterministic ordering so diffs are clean across rewrites.
    lines = [f"{k}={v}" for k, v in sorted(existing.items())]
    content = "\n".join(lines) + ("\n" if lines else "")

    # Atomic: write to sibling tempfile, chmod, replace.
    fd, tmp_path = tempfile.mkstemp(prefix=".env-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    except Exception:
        # Best-effort cleanup; re-raise.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return path
