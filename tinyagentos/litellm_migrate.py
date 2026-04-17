"""Auto-apply LiteLLM's Prisma schema at taOS startup.

LiteLLM ships a ``schema.prisma`` inside its installed package but does
not run migrations itself. On a fresh install with Postgres configured,
the ``/key/generate`` endpoint fails until somebody manually runs:

    pip install prisma
    prisma generate --schema=<litellm>/schema.prisma
    DATABASE_URL=... prisma db push --accept-data-loss --schema=<litellm>/schema.prisma

This module does that automatically — idempotently — on every boot when
``data/.litellm_db_url`` is present. If the expected LiteLLM table is
already there, it no-ops.

Must run BEFORE ``LLMProxy.start()`` so LiteLLM sees a ready schema when
it connects.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Any LiteLLM table works as a "schema present" probe. VerificationToken
# is core to /key/generate and has been stable across the LiteLLM
# versions taOS targets (>=1.50).
_PROBE_TABLE = "LiteLLM_VerificationToken"


def _prisma_cli() -> str:
    """Path to the ``prisma`` CLI installed in the current venv.

    The pip ``prisma`` package drops a ``prisma`` binary next to
    ``python`` in the venv's ``bin/``. Falling back to ``sys.executable
    -m prisma`` is unreliable because the package's ``__main__`` isn't a
    proper CLI entrypoint — the shipped binary is.
    """
    return str(Path(sys.executable).parent / "prisma")


def _schema_path() -> Path | None:
    """Locate the LiteLLM-bundled ``schema.prisma`` file.

    Returns None if LiteLLM isn't installed or the schema file is
    missing — callers log and bail.
    """
    try:
        import litellm.proxy  # type: ignore
    except Exception as exc:
        logger.error("litellm_migrate: cannot import litellm.proxy: %s", exc)
        return None
    path = Path(litellm.proxy.__file__).parent / "schema.prisma"
    if not path.exists():
        logger.error("litellm_migrate: schema not found at %s", path)
        return None
    return path


def _schema_already_applied(db_url: str) -> bool:
    """True iff the probe table exists in the target database.

    Uses psycopg's pure-Python path if available; falls back to a raw
    socket-less check by asking Postgres via ``psql`` if present. The
    helper must never raise: on any error it returns False so the
    migration runs and surfaces the real problem.
    """
    try:
        # psycopg2 / psycopg3 either: LiteLLM pulls one of them in as a
        # transitive dep, so importing here is safe on any system that
        # has LiteLLM proxy installed.
        try:
            import psycopg2  # type: ignore
            conn = psycopg2.connect(db_url)
        except ImportError:
            import psycopg  # type: ignore
            conn = psycopg.connect(db_url)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT to_regclass(%s) IS NOT NULL",
                (f"public.\"{_PROBE_TABLE}\"",),
            )
            row = cur.fetchone()
            return bool(row and row[0])
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("litellm_migrate: probe failed (%s) — will attempt migration", exc)
        return False


def _run(cmd: list[str], env: dict[str, str]) -> None:
    """Run a subprocess, log output, raise on non-zero exit.

    We want taOS boot to fail loudly if migration fails — LiteLLM will
    otherwise serve requests but silently 500 on /key/generate, which
    is far worse than a visible startup error.
    """
    logger.info("litellm_migrate: running %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout.strip():
        logger.info("litellm_migrate stdout: %s", result.stdout.strip())
    if result.stderr.strip():
        logger.info("litellm_migrate stderr: %s", result.stderr.strip())
    if result.returncode != 0:
        raise RuntimeError(
            f"litellm_migrate: {' '.join(cmd)} exited {result.returncode}"
        )


def migrate(data_dir: Path) -> str:
    """Apply LiteLLM's Prisma schema if Postgres is configured.

    Returns a short status string for logging/tests:
        - "no-db"          → no ``.litellm_db_url`` file, nothing to do
        - "already-applied" → probe table exists, no migration needed
        - "applied"        → prisma generate + db push ran successfully

    Raises on any failure of the CLI subprocess calls so the error
    surfaces at taOS boot instead of later at /key/generate time.
    """
    db_url_path = data_dir / ".litellm_db_url"
    if not db_url_path.exists():
        logger.info("litellm_migrate: no .litellm_db_url — skipping")
        return "no-db"
    db_url = db_url_path.read_text().strip()
    if not db_url:
        logger.info("litellm_migrate: .litellm_db_url empty — skipping")
        return "no-db"

    schema = _schema_path()
    if schema is None:
        # Error already logged in _schema_path.
        return "no-schema"

    if _schema_already_applied(db_url):
        logger.info(
            "litellm_migrate: %s present in %s — migration already applied",
            _PROBE_TABLE,
            urlparse(db_url).path.lstrip("/") or "<db>",
        )
        return "already-applied"

    cli = _prisma_cli()
    if not Path(cli).exists():
        raise RuntimeError(
            f"litellm_migrate: prisma CLI not found at {cli} — "
            "is the 'prisma' pip package installed in this venv?"
        )

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url

    _run([cli, "generate", f"--schema={schema}"], env)
    _run([cli, "db", "push", "--accept-data-loss", f"--schema={schema}"], env)

    if not _schema_already_applied(db_url):
        raise RuntimeError(
            "litellm_migrate: migration ran but probe table still missing"
        )
    logger.info("litellm_migrate: migration applied against %s", schema)
    return "applied"
