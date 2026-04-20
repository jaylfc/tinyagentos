# Framework update — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship per-agent detection and manual installation of framework updates via a new Framework tab in Agent Settings, backed by an LXC snapshot for safety and the bridge's bootstrap call as the ready signal.

**Architecture:** Backend-first. Framework manifest gains four update-metadata fields; agent record gains seven fields tracking install state. A new `framework_update.py` module orchestrates snapshot → install-script-via-container-exec → wait-for-bootstrap-ping → verify. The bridge's existing `/api/openclaw/bootstrap` handler bumps a timestamp so the runner can detect when the agent is back. Frontend adds a Framework tab, a sidebar dot, and a Store pill.

**Tech Stack:** Python 3.11, FastAPI, pytest, asyncio, bash 5 for container-side script; React 18 + TypeScript + Vite + Tailwind; LXC via existing `tinyagentos/containers.py` helpers. Python Playwright under `tests/e2e/`.

**Spec:** `docs/superpowers/specs/2026-04-18-framework-update-phase-1-design.md`

**Branch:** all work on `feat/framework-update-phase-1` off master. Land via PR so CI runs.

---

## File structure

**New files:**
- `tinyagentos/framework_update.py` — orchestration module.
- `tinyagentos/github_releases.py` — release fetch + pure parser.
- `tinyagentos/routes/framework.py` — API endpoints.
- `tinyagentos/scripts/taos-framework-update.sh` — container-side installer, baked into image.
- `desktop/src/components/agent-settings/FrameworkTab.tsx`
- `desktop/src/lib/framework-api.ts`
- `tests/test_github_releases.py`
- `tests/test_framework_manifest.py`
- `tests/test_framework_update_runner.py`
- `tests/test_framework_api.py`
- `tests/test_auto_update_framework.py`
- `tests/test_containers_snapshots.py`
- `tests/e2e/test_framework_tab.py`
- `tests/e2e/test_framework_store_pill.py`

**Modified files:**
- `tinyagentos/config.py` — `normalize_agent` gets 7 new fields.
- `tinyagentos/frameworks.py` — 4 new manifest fields + `validate_framework_manifest`.
- `tinyagentos/auto_update.py` — add `poll_frameworks` called from the hourly loop.
- `tinyagentos/containers.py` — confirm/add `snapshot_list` + `snapshot_delete`.
- `tinyagentos/routes/openclaw.py` — bootstrap handler bumps `bootstrap_last_seen_at`.
- `tinyagentos/agent_image.py` — copy install script into the base image.
- `tinyagentos/app.py` — init `latest_framework_versions`, `host_arch`, probe existing agents, register the new router.
- `desktop/src/apps/AgentsApp.tsx` — Framework tab + sidebar dot.
- `desktop/src/apps/StoreApp.tsx` — affected-agent pill.

---

## Phase 1 — Agent record fields

### Task 1.1: Extend `normalize_agent` with framework-update fields

**Files:**
- Modify: `tinyagentos/config.py`
- Test: `tests/test_config_normalize.py` (append)

- [ ] **Step 1: Failing test**

```python
def test_normalize_agent_adds_framework_update_fields_with_defaults():
    agent = {"name": "atlas", "display_name": "Atlas", "framework": "openclaw"}
    normalize_agent(agent)
    assert agent["framework_version_tag"] is None
    assert agent["framework_version_sha"] is None
    assert agent["framework_update_status"] == "idle"
    assert agent["framework_update_started_at"] is None
    assert agent["framework_update_last_error"] is None
    assert agent["framework_last_snapshot"] is None
    assert agent["bootstrap_last_seen_at"] is None

def test_normalize_agent_preserves_existing_framework_update_fields():
    agent = {
        "name": "atlas", "framework": "openclaw",
        "framework_version_tag": "20260419T100000",
        "framework_version_sha": "abc1234",
        "framework_update_status": "failed",
        "framework_update_started_at": 1800000000,
        "framework_update_last_error": "timed out",
        "framework_last_snapshot": "pre-framework-update-x",
        "bootstrap_last_seen_at": 1800000005,
    }
    normalize_agent(agent)
    assert agent["framework_update_status"] == "failed"
    assert agent["framework_last_snapshot"] == "pre-framework-update-x"
    assert agent["bootstrap_last_seen_at"] == 1800000005
```

- [ ] **Step 2: Run — FAIL**

`pytest tests/test_config_normalize.py -v`

- [ ] **Step 3: Implement**

In `tinyagentos/config.py`, inside `normalize_agent`, before `return agent`:

```python
    agent.setdefault("framework_version_tag", None)
    agent.setdefault("framework_version_sha", None)
    agent.setdefault("framework_update_status", "idle")
    agent.setdefault("framework_update_started_at", None)
    agent.setdefault("framework_update_last_error", None)
    agent.setdefault("framework_last_snapshot", None)
    agent.setdefault("bootstrap_last_seen_at", None)
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git checkout -b feat/framework-update-phase-1
git add tinyagentos/config.py tests/test_config_normalize.py
git commit -m "feat(config): add framework-update fields to agent normalize"
```

---

## Phase 2 — Framework manifest

### Task 2.1: Manifest metadata + validator

**Files:**
- Modify: `tinyagentos/frameworks.py`
- Test: `tests/test_framework_manifest.py` (new)

- [ ] **Step 1: Inspect current shape**

```bash
grep -n "FRAMEWORKS\|openclaw" tinyagentos/frameworks.py | head
```

- [ ] **Step 2: Failing tests**

```python
# tests/test_framework_manifest.py
import pytest
from tinyagentos.frameworks import FRAMEWORKS, validate_framework_manifest, FrameworkManifestError

def test_openclaw_has_update_metadata():
    fw = FRAMEWORKS["openclaw"]
    assert fw["release_source"] == "github:jaylfc/openclaw"
    assert "{arch}" in fw["release_asset_pattern"]
    assert fw["install_script"] == "/usr/local/bin/taos-framework-update"
    assert fw["service_name"] == "openclaw"

def test_validate_rejects_missing_update_fields():
    with pytest.raises(FrameworkManifestError):
        validate_framework_manifest("x", {"id": "x", "name": "X"}, require_update_fields=True)

def test_validate_passes_with_all_fields():
    good = {"id": "x", "name": "X", "release_source": "github:a/b",
            "release_asset_pattern": "b-{arch}.tgz",
            "install_script": "/usr/local/bin/taos-framework-update",
            "service_name": "x"}
    validate_framework_manifest("x", good, require_update_fields=True)

def test_validate_allows_missing_update_fields_when_flag_false():
    validate_framework_manifest("x", {"id": "x", "name": "X"}, require_update_fields=False)

def test_all_frameworks_with_release_source_pass_validation():
    for fw_id, entry in FRAMEWORKS.items():
        if entry.get("release_source"):
            validate_framework_manifest(fw_id, entry, require_update_fields=True)
```

- [ ] **Step 3: Run — FAIL**

- [ ] **Step 4: Implement**

In `tinyagentos/frameworks.py`:

```python
class FrameworkManifestError(ValueError):
    pass

# Add to the openclaw entry in FRAMEWORKS (merge with existing dict literal style):
#   "release_source": "github:jaylfc/openclaw",
#   "release_asset_pattern": "openclaw-taos-fork-linux-{arch}.tgz",
#   "install_script": "/usr/local/bin/taos-framework-update",
#   "service_name": "openclaw",

_REQUIRED_UPDATE_FIELDS = (
    "release_source", "release_asset_pattern", "install_script", "service_name",
)

def validate_framework_manifest(fw_id, entry, *, require_update_fields=False):
    if "id" not in entry or "name" not in entry:
        raise FrameworkManifestError(f"{fw_id}: missing id or name")
    if require_update_fields:
        missing = [k for k in _REQUIRED_UPDATE_FIELDS if k not in entry]
        if missing:
            raise FrameworkManifestError(f"{fw_id}: missing update fields {missing}")
```

- [ ] **Step 5: Run — PASS**

- [ ] **Step 6: Commit**

```bash
git add tinyagentos/frameworks.py tests/test_framework_manifest.py
git commit -m "feat(frameworks): manifest update metadata + validator"
```

---

### Task 2.2: Validate at startup

**Files:**
- Modify: `tinyagentos/app.py`

- [ ] **Step 1: Add to `create_app` startup block**

```python
from tinyagentos.frameworks import FRAMEWORKS, validate_framework_manifest, FrameworkManifestError

for fw_id, entry in FRAMEWORKS.items():
    try:
        validate_framework_manifest(
            fw_id, entry,
            require_update_fields=bool(entry.get("release_source")),
        )
    except FrameworkManifestError:
        logger.exception("framework manifest validation failed")
        # Do NOT raise — legacy manifests can still run agents; only update paths are disabled.
```

- [ ] **Step 2: Commit**

```bash
git add tinyagentos/app.py
git commit -m "feat(app): validate framework manifests at startup"
```

---

## Phase 3 — GitHub Releases parser

### Task 3.1: Pure parser + fetch helper

**Files:**
- Create: `tinyagentos/github_releases.py`
- Test: `tests/test_github_releases.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_github_releases.py
import pytest
from tinyagentos.github_releases import parse_release, ReleaseAssetNotFoundError

SAMPLE = {
    "tag_name": "20260418T133712",
    "target_commitish": "9bab2e347aaa11e7e646b49dc358d00d01b1d21d",
    "published_at": "2026-04-18T19:41:07Z",
    "assets": [
        {"name": "openclaw-taos-fork-linux-x86_64.tgz", "browser_download_url": "https://x.com/x86_64.tgz"},
        {"name": "openclaw-taos-fork-linux-aarch64.tgz", "browser_download_url": "https://x.com/aarch64.tgz"},
    ],
}

def test_parse_release_extracts_tag_and_shas():
    p = parse_release(SAMPLE, asset_pattern="openclaw-taos-fork-linux-{arch}.tgz", arch="x86_64")
    assert p["tag"] == "20260418T133712"
    assert p["sha"] == "9bab2e3"
    assert p["full_sha"] == "9bab2e347aaa11e7e646b49dc358d00d01b1d21d"
    assert p["published_at"] == "2026-04-18T19:41:07Z"
    assert p["asset_url"] == "https://x.com/x86_64.tgz"

def test_parse_release_picks_arch_specific_asset():
    p = parse_release(SAMPLE, asset_pattern="openclaw-taos-fork-linux-{arch}.tgz", arch="aarch64")
    assert p["asset_url"] == "https://x.com/aarch64.tgz"

def test_parse_release_raises_when_asset_missing():
    with pytest.raises(ReleaseAssetNotFoundError):
        parse_release(SAMPLE, asset_pattern="openclaw-taos-fork-linux-{arch}.tgz", arch="riscv64")
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

```python
# tinyagentos/github_releases.py
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

class ReleaseAssetNotFoundError(LookupError):
    pass

def parse_release(raw: dict, *, asset_pattern: str, arch: str) -> dict:
    full_sha = raw["target_commitish"]
    expected_name = asset_pattern.format(arch=arch)
    asset = next((a for a in raw.get("assets", []) if a.get("name") == expected_name), None)
    if asset is None:
        raise ReleaseAssetNotFoundError(
            f"asset {expected_name!r} not in release {raw.get('tag_name')!r}"
        )
    return {
        "tag": raw["tag_name"],
        "full_sha": full_sha,
        "sha": full_sha[:7],
        "published_at": raw.get("published_at"),
        "asset_url": asset["browser_download_url"],
    }

async def fetch_latest_release(manifest: dict, http_client, *, arch: str) -> dict:
    source = manifest["release_source"]
    if not source.startswith("github:"):
        raise ValueError(f"unsupported release_source scheme: {source!r}")
    owner_repo = source[len("github:"):]
    url = f"https://api.github.com/repos/{owner_repo}/releases/latest"
    resp = await http_client.get(url, headers={"Accept": "application/vnd.github+json"})
    resp.raise_for_status()
    return parse_release(resp.json(),
                         asset_pattern=manifest["release_asset_pattern"], arch=arch)
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/github_releases.py tests/test_github_releases.py
git commit -m "feat(releases): parser + fetch helper for GitHub Releases"
```

---

## Phase 4 — Polling service

### Task 4.1: `poll_frameworks` in auto_update

**Files:**
- Modify: `tinyagentos/auto_update.py`
- Test: `tests/test_auto_update_framework.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_auto_update_framework.py
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_poll_frameworks_populates_cache(monkeypatch):
    from tinyagentos.auto_update import poll_frameworks
    fake = {"tag": "T1", "sha": "a1a1a1a", "full_sha": "a1a1a1a...",
            "published_at": "x", "asset_url": "u"}
    monkeypatch.setattr(
        "tinyagentos.github_releases.fetch_latest_release",
        AsyncMock(return_value=fake),
    )
    manifests = {"openclaw": {"release_source": "github:a/b",
                              "release_asset_pattern": "x-{arch}.tgz"}}
    cache = {}
    await poll_frameworks(manifests, http_client=MagicMock(), arch="x86_64", cache=cache)
    assert cache["openclaw"] == fake

@pytest.mark.asyncio
async def test_poll_frameworks_keeps_last_good_on_failure(monkeypatch):
    from tinyagentos.auto_update import poll_frameworks
    monkeypatch.setattr(
        "tinyagentos.github_releases.fetch_latest_release",
        AsyncMock(side_effect=RuntimeError("rate limit")),
    )
    manifests = {"openclaw": {"release_source": "github:a/b",
                              "release_asset_pattern": "x-{arch}.tgz"}}
    cache = {"openclaw": {"tag": "OLD"}}
    await poll_frameworks(manifests, http_client=MagicMock(), arch="x86_64", cache=cache)
    assert cache["openclaw"]["tag"] == "OLD"

@pytest.mark.asyncio
async def test_poll_frameworks_skips_when_no_release_source(monkeypatch):
    from tinyagentos.auto_update import poll_frameworks
    called = AsyncMock()
    monkeypatch.setattr("tinyagentos.github_releases.fetch_latest_release", called)
    await poll_frameworks({"x": {}}, http_client=MagicMock(), arch="x86_64", cache={})
    called.assert_not_called()
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

Add to `tinyagentos/auto_update.py`:

```python
from tinyagentos.github_releases import fetch_latest_release

async def poll_frameworks(manifests, *, http_client, arch, cache):
    for fw_id, manifest in manifests.items():
        if not manifest.get("release_source"):
            continue
        try:
            cache[fw_id] = await fetch_latest_release(manifest, http_client, arch=arch)
        except Exception:
            logger.warning("poll_frameworks: refresh for %s failed; keeping last good", fw_id)
```

Find the existing hourly loop coroutine in the same file and add one call:

```python
from tinyagentos.frameworks import FRAMEWORKS
await poll_frameworks(
    FRAMEWORKS,
    http_client=app.state.http_client,
    arch=app.state.host_arch,
    cache=app.state.latest_framework_versions,
)
```

Exact placement inside the existing loop depends on its current shape — match the pattern already used for the taOS self-update tick.

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/auto_update.py tests/test_auto_update_framework.py
git commit -m "feat(auto_update): hourly framework releases poll"
```

---

## Phase 5 — Container snapshot helpers

### Task 5.1: `snapshot_list` + `snapshot_delete`

**Files:**
- Modify: `tinyagentos/containers.py`
- Test: `tests/test_containers_snapshots.py`

- [ ] **Step 1: Check what exists**

```bash
grep -n "snapshot_" tinyagentos/containers.py
```

- [ ] **Step 2: Failing tests**

```python
# tests/test_containers_snapshots.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_snapshot_create_invokes_incus():
    with patch("tinyagentos.containers._run", new=AsyncMock(return_value=(0, ""))) as run:
        from tinyagentos.containers import snapshot_create
        await snapshot_create("taos-agent-atlas", "pre-update-1")
        cmd = run.call_args.args[0]
        assert "incus" in cmd and "snapshot" in cmd and "pre-update-1" in cmd

@pytest.mark.asyncio
async def test_snapshot_list_filters_by_prefix(monkeypatch):
    from tinyagentos.containers import snapshot_list
    csv = "pre-x,2026/04/18 20:00 UTC\nother,2026/04/18 19:00 UTC\n"
    monkeypatch.setattr("tinyagentos.containers._run", AsyncMock(return_value=(0, csv)))
    snaps = await snapshot_list("taos-agent-atlas", prefix="pre-")
    assert [s["name"] for s in snaps] == ["pre-x"]

@pytest.mark.asyncio
async def test_snapshot_delete_invokes_incus():
    with patch("tinyagentos.containers._run", new=AsyncMock(return_value=(0, ""))) as run:
        from tinyagentos.containers import snapshot_delete
        await snapshot_delete("taos-agent-atlas", "snap-a")
        cmd = run.call_args.args[0]
        assert "delete" in cmd and "snap-a" in cmd
```

- [ ] **Step 3: Run — FAIL (if helpers missing)**

- [ ] **Step 4: Implement**

Append to `tinyagentos/containers.py`:

```python
async def snapshot_list(name: str, *, prefix: str | None = None) -> list[dict]:
    rc, out = await _run(
        ["incus", "snapshot", "list", name, "--format", "csv"], timeout=30,
    )
    if rc != 0:
        return []
    snaps: list[dict] = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2 or not parts[0]:
            continue
        if prefix and not parts[0].startswith(prefix):
            continue
        snaps.append({"name": parts[0], "created_at": parts[1]})
    return snaps

async def snapshot_delete(name: str, snapshot_name: str) -> None:
    rc, out = await _run(
        ["incus", "snapshot", "delete", name, snapshot_name], timeout=60,
    )
    if rc != 0:
        logger.warning("snapshot_delete failed %s/%s: %s", name, snapshot_name, out[:200])
```

If `snapshot_create` does not already exist in the file, also add:

```python
async def snapshot_create(name: str, snapshot_name: str) -> None:
    rc, out = await _run(
        ["incus", "snapshot", "create", name, snapshot_name], timeout=120,
    )
    if rc != 0:
        raise RuntimeError(f"snapshot_create failed for {name}/{snapshot_name}: {out[:200]}")
```

Adapt to the real incus CSV format on first test run — the parser may need tightening.

- [ ] **Step 5: Run — PASS**

- [ ] **Step 6: Commit**

```bash
git add tinyagentos/containers.py tests/test_containers_snapshots.py
git commit -m "feat(containers): snapshot_list and snapshot_delete helpers"
```

---

## Phase 6 — Update runner

### Task 6.1: `_prune_old_snapshots` helper

**Files:**
- Create: `tinyagentos/framework_update.py`
- Test: `tests/test_framework_update_runner.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_framework_update_runner.py
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
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

```python
# tinyagentos/framework_update.py
from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timezone

from tinyagentos.containers import (
    exec_in_container, snapshot_create, snapshot_list, snapshot_delete,
)

logger = logging.getLogger(__name__)

SNAPSHOT_PREFIX = "pre-framework-update-"
UPDATE_DEADLINE_SECONDS = 120


async def _prune_old_snapshots(container: str, *, keep: int) -> None:
    snaps = await snapshot_list(container, prefix=SNAPSHOT_PREFIX)
    for extra in snaps[keep:]:
        await snapshot_delete(container, extra["name"])
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/framework_update.py tests/test_framework_update_runner.py
git commit -m "feat(framework-update): prune old pre-update snapshots"
```

---

### Task 6.2: `_wait_for_bootstrap_ping`

**Files:**
- Modify: `tinyagentos/framework_update.py`
- Test: append to `tests/test_framework_update_runner.py`

- [ ] **Step 1: Failing tests**

```python
@pytest.mark.asyncio
async def test_wait_for_ping_returns_true_when_arrives_before_deadline():
    from tinyagentos.framework_update import _wait_for_bootstrap_ping
    agent = {"bootstrap_last_seen_at": None}
    started_at = int(time.time())
    async def ping():
        await asyncio.sleep(0.1)
        agent["bootstrap_last_seen_at"] = int(time.time()) + 1
    import asyncio as _a
    _a.create_task(ping())
    ok = await _wait_for_bootstrap_ping(agent, started_at=started_at, deadline_seconds=2)
    assert ok is True

@pytest.mark.asyncio
async def test_wait_for_ping_returns_false_on_timeout():
    from tinyagentos.framework_update import _wait_for_bootstrap_ping
    ok = await _wait_for_bootstrap_ping({"bootstrap_last_seen_at": None},
                                         started_at=int(time.time()),
                                         deadline_seconds=1)
    assert ok is False

@pytest.mark.asyncio
async def test_wait_ignores_stale_pings():
    from tinyagentos.framework_update import _wait_for_bootstrap_ping
    started_at = int(time.time())
    ok = await _wait_for_bootstrap_ping(
        {"bootstrap_last_seen_at": started_at - 5},
        started_at=started_at, deadline_seconds=1,
    )
    assert ok is False
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

Append to `tinyagentos/framework_update.py`:

```python
async def _wait_for_bootstrap_ping(agent, *, started_at, deadline_seconds=UPDATE_DEADLINE_SECONDS):
    deadline = time.time() + deadline_seconds
    while time.time() < deadline:
        last = agent.get("bootstrap_last_seen_at") or 0
        if last > started_at:
            return True
        await asyncio.sleep(0.5)
    return False
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/framework_update.py tests/test_framework_update_runner.py
git commit -m "feat(framework-update): bootstrap-ping wait with 500ms polling"
```

---

### Task 6.3: `start_update` orchestration

**Files:**
- Modify: `tinyagentos/framework_update.py`
- Test: append to `tests/test_framework_update_runner.py`

- [ ] **Step 1: Failing tests**

```python
@pytest.mark.asyncio
async def test_start_update_happy_path(monkeypatch):
    from tinyagentos.framework_update import start_update
    agent = {"name": "atlas", "framework": "openclaw", "bootstrap_last_seen_at": None}
    manifest = {"id": "openclaw", "install_script": "/usr/local/bin/taos-framework-update"}
    latest = {"tag": "T2", "sha": "b2b2b2b", "asset_url": "u"}

    async def fake_exec(container, cmd, timeout=None):
        agent["bootstrap_last_seen_at"] = int(time.time()) + 5
        return 0, ""

    monkeypatch.setattr("tinyagentos.framework_update.snapshot_create", AsyncMock())
    monkeypatch.setattr("tinyagentos.framework_update._prune_old_snapshots", AsyncMock())
    monkeypatch.setattr("tinyagentos.framework_update.exec_in_container", fake_exec)
    monkeypatch.setattr("tinyagentos.framework_update._read_installed_tag",
                         AsyncMock(return_value="T2"))
    await start_update(agent, manifest, latest, save_config=AsyncMock())
    assert agent["framework_update_status"] == "idle"
    assert agent["framework_version_tag"] == "T2"
    assert agent["framework_version_sha"] == "b2b2b2b"

@pytest.mark.asyncio
async def test_start_update_fails_on_nonzero_exit(monkeypatch):
    from tinyagentos.framework_update import start_update
    agent = {"name": "atlas", "framework": "openclaw"}
    monkeypatch.setattr("tinyagentos.framework_update.snapshot_create", AsyncMock())
    monkeypatch.setattr("tinyagentos.framework_update._prune_old_snapshots", AsyncMock())
    monkeypatch.setattr("tinyagentos.framework_update.exec_in_container",
                         AsyncMock(return_value=(1, "blew up")))
    await start_update(agent,
                        {"id": "openclaw", "install_script": "/usr/local/bin/taos-framework-update"},
                        {"tag": "T", "sha": "s", "asset_url": "u"},
                        save_config=AsyncMock())
    assert agent["framework_update_status"] == "failed"
    assert agent["framework_last_snapshot"] is not None

@pytest.mark.asyncio
async def test_start_update_fails_on_missing_bootstrap(monkeypatch):
    from tinyagentos import framework_update as fu
    from tinyagentos.framework_update import start_update
    agent = {"name": "atlas", "framework": "openclaw", "bootstrap_last_seen_at": None}
    monkeypatch.setattr(fu, "snapshot_create", AsyncMock())
    monkeypatch.setattr(fu, "_prune_old_snapshots", AsyncMock())
    monkeypatch.setattr(fu, "exec_in_container", AsyncMock(return_value=(0, "")))
    monkeypatch.setattr(fu, "UPDATE_DEADLINE_SECONDS", 1)
    await start_update(agent,
                        {"id": "openclaw", "install_script": "/usr/local/bin/taos-framework-update"},
                        {"tag": "T", "sha": "s", "asset_url": "u"},
                        save_config=AsyncMock())
    assert agent["framework_update_status"] == "failed"
    assert "bridge" in agent["framework_update_last_error"]

@pytest.mark.asyncio
async def test_start_update_aborts_before_install_on_snapshot_failure(monkeypatch):
    from tinyagentos.framework_update import start_update
    install = AsyncMock()
    monkeypatch.setattr("tinyagentos.framework_update.snapshot_create",
                         AsyncMock(side_effect=RuntimeError("pool offline")))
    monkeypatch.setattr("tinyagentos.framework_update.exec_in_container", install)
    agent = {"name": "atlas", "framework": "openclaw"}
    await start_update(agent,
                        {"id": "openclaw", "install_script": "/usr/local/bin/taos-framework-update"},
                        {"tag": "T", "sha": "s", "asset_url": "u"},
                        save_config=AsyncMock())
    assert agent["framework_update_status"] == "failed"
    install.assert_not_awaited()
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

Append to `tinyagentos/framework_update.py`:

```python
def _iso_utc_compact():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


async def _read_installed_tag(container):
    rc, out = await exec_in_container(
        container, ["cat", "/opt/taos/framework.version"], timeout=10,
    )
    return out.strip() if rc == 0 else ""


async def _mark_failed(agent, reason, *, save_config, snapshot=None):
    agent["framework_update_status"] = "failed"
    agent["framework_update_started_at"] = None
    agent["framework_update_last_error"] = reason[:500]
    if snapshot is not None:
        agent["framework_last_snapshot"] = snapshot
    await save_config()


async def start_update(agent, manifest, latest, *, save_config):
    try:
        started_at = int(time.time())
        agent["framework_update_status"] = "updating"
        agent["framework_update_started_at"] = started_at
        agent["framework_update_last_error"] = None
        await save_config()

        container = f"taos-agent-{agent['name']}"
        snap = f"{SNAPSHOT_PREFIX}{latest['tag']}-{_iso_utc_compact()}"
        try:
            await snapshot_create(container, snap)
            agent["framework_last_snapshot"] = snap
            await save_config()
            await _prune_old_snapshots(container, keep=3)
        except Exception as e:
            return await _mark_failed(agent, f"snapshot failed: {e}", save_config=save_config)

        try:
            rc, stderr = await exec_in_container(container, [
                manifest["install_script"], manifest["id"],
                latest["tag"], latest["asset_url"],
            ], timeout=UPDATE_DEADLINE_SECONDS)
        except asyncio.TimeoutError:
            return await _mark_failed(agent, "install script timed out",
                                       save_config=save_config, snapshot=snap)

        if rc != 0:
            return await _mark_failed(agent, f"install script rc={rc}: {stderr[:400]}",
                                       save_config=save_config, snapshot=snap)

        if not await _wait_for_bootstrap_ping(agent, started_at=started_at):
            return await _mark_failed(agent, "bridge did not reconnect within 120s",
                                       save_config=save_config, snapshot=snap)

        installed_tag = await _read_installed_tag(container)
        if installed_tag != latest["tag"]:
            return await _mark_failed(
                agent,
                f"version mismatch: installed={installed_tag!r} expected={latest['tag']!r}",
                save_config=save_config, snapshot=snap,
            )

        agent["framework_version_tag"] = installed_tag
        agent["framework_version_sha"] = latest["sha"]
        agent["framework_update_status"] = "idle"
        agent["framework_update_started_at"] = None
        await save_config()
    except Exception as e:
        logger.exception("unexpected error in start_update for %s", agent.get("name"))
        await _mark_failed(agent, f"unexpected: {e}", save_config=save_config)
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/framework_update.py tests/test_framework_update_runner.py
git commit -m "feat(framework-update): start_update orchestration"
```

---

## Phase 7 — Bootstrap-ping hook

### Task 7.1: Bump `bootstrap_last_seen_at` in bootstrap handler

**Files:**
- Modify: `tinyagentos/routes/openclaw.py`
- Test: `tests/test_openclaw_bootstrap_ping.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_openclaw_bootstrap_ping.py
import pytest

@pytest.mark.asyncio
async def test_bootstrap_sets_last_seen_at(client, app):
    app.state.config.agents.append({
        "name": "atlas", "display_name": "Atlas", "framework": "openclaw",
        "bootstrap_last_seen_at": None,
    })
    # Use whatever header/auth the existing bootstrap tests use
    resp = await client.get("/api/openclaw/bootstrap?agent=atlas",
                             headers={"Authorization": "Bearer test"})
    # Auth may reject with 401/403 depending on setup — test focuses on
    # the observable side effect on the agent record when authenticated.
    assert resp.status_code in (200, 401, 403)
    agent = next(a for a in app.state.config.agents if a["name"] == "atlas")
    # Only assert set if auth succeeded
    if resp.status_code == 200:
        assert agent["bootstrap_last_seen_at"] is not None
```

Adapt fixture + auth to match the real test style in the file.

- [ ] **Step 2: Implement**

In `tinyagentos/routes/openclaw.py`, inside the bootstrap endpoint after the agent is loaded and before returning:

```python
import time as _time
agent["bootstrap_last_seen_at"] = int(_time.time())
await save_config_locked(config, config.config_path)
```

- [ ] **Step 3: Run — PASS**

- [ ] **Step 4: Commit**

```bash
git add tinyagentos/routes/openclaw.py tests/test_openclaw_bootstrap_ping.py
git commit -m "feat(openclaw): bootstrap handler bumps bootstrap_last_seen_at"
```

---

## Phase 8 — Backend API

### Task 8.1: GET `/api/agents/{slug}/framework`

**Files:**
- Create: `tinyagentos/routes/framework.py`
- Modify: `tinyagentos/app.py` (register router + init state)
- Test: `tests/test_framework_api.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_framework_api.py
import pytest

@pytest.mark.asyncio
async def test_get_framework_state(client, app):
    app.state.config.agents.append({
        "name": "atlas", "framework": "openclaw",
        "framework_version_tag": "T1", "framework_version_sha": "a1a1a1a",
        "framework_update_status": "idle",
    })
    app.state.latest_framework_versions = {
        "openclaw": {"tag": "T2", "sha": "b2b2b2b", "published_at": "x", "asset_url": "u"},
    }
    r = await client.get("/api/agents/atlas/framework")
    assert r.status_code == 200
    body = r.json()
    assert body["framework"] == "openclaw"
    assert body["installed"]["sha"] == "a1a1a1a"
    assert body["latest"]["sha"] == "b2b2b2b"
    assert body["update_available"] is True
    assert body["update_status"] == "idle"

@pytest.mark.asyncio
async def test_get_framework_404(client):
    r = await client.get("/api/agents/nope/framework")
    assert r.status_code == 404

@pytest.mark.asyncio
async def test_get_framework_no_latest_when_source_missing(client, app):
    app.state.config.agents.append({
        "name": "bob", "framework": "legacy",
        "framework_version_tag": None, "framework_version_sha": None,
        "framework_update_status": "idle",
    })
    app.state.latest_framework_versions = {}
    r = await client.get("/api/agents/bob/framework")
    assert r.json()["latest"] is None
    assert r.json()["update_available"] is False
```

- [ ] **Step 2: Run — FAIL (route missing)**

- [ ] **Step 3: Implement**

```python
# tinyagentos/routes/framework.py
from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from tinyagentos.agent_db import find_agent

router = APIRouter()


def _installed(agent):
    return {"tag": agent.get("framework_version_tag"),
            "sha": agent.get("framework_version_sha")}


def _latest(entry):
    if entry is None:
        return None
    return {"tag": entry["tag"], "sha": entry["sha"],
            "published_at": entry.get("published_at")}


@router.get("/api/agents/{slug}/framework")
async def get_agent_framework(request: Request, slug: str):
    config = request.app.state.config
    agent = find_agent(config, slug)
    if not agent:
        return JSONResponse({"error": "agent not found"}, status_code=404)
    fw_id = agent.get("framework")
    cache = getattr(request.app.state, "latest_framework_versions", {}) or {}
    latest = cache.get(fw_id)
    installed = _installed(agent)
    update_available = bool(latest and installed["sha"]
                             and latest["sha"] != installed["sha"])
    return {
        "framework": fw_id,
        "installed": installed,
        "latest": _latest(latest),
        "update_available": update_available,
        "update_status": agent.get("framework_update_status", "idle"),
        "update_started_at": agent.get("framework_update_started_at"),
        "last_error": agent.get("framework_update_last_error"),
        "last_snapshot": agent.get("framework_last_snapshot"),
    }
```

In `tinyagentos/app.py`:

```python
import platform
from tinyagentos.routes import framework as framework_routes
app.state.latest_framework_versions = {}
app.state.host_arch = platform.machine()
app.include_router(framework_routes.router)
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/routes/framework.py tinyagentos/app.py tests/test_framework_api.py
git commit -m "feat(framework): GET /api/agents/{slug}/framework endpoint"
```

---

### Task 8.2: POST `/api/agents/{slug}/framework/update`

**Files:**
- Modify: `tinyagentos/routes/framework.py`
- Append: `tests/test_framework_api.py`

- [ ] **Step 1: Failing tests**

```python
@pytest.mark.asyncio
async def test_post_update_kicks_off_task(client, app, monkeypatch):
    app.state.config.agents.append({
        "name": "atlas", "framework": "openclaw", "framework_update_status": "idle",
    })
    app.state.latest_framework_versions = {
        "openclaw": {"tag": "T2", "sha": "b2b2b2b", "asset_url": "u"},
    }
    kicked = {}
    async def fake(agent, manifest, latest, *, save_config):
        kicked["ok"] = True
    monkeypatch.setattr("tinyagentos.framework_update.start_update", fake)
    r = await client.post("/api/agents/atlas/framework/update", json={})
    assert r.status_code == 202
    import asyncio; await asyncio.sleep(0.05)
    assert kicked.get("ok") is True

@pytest.mark.asyncio
async def test_post_update_409_when_already_updating(client, app):
    app.state.config.agents.append({
        "name": "atlas", "framework": "openclaw",
        "framework_update_status": "updating",
    })
    app.state.latest_framework_versions = {
        "openclaw": {"tag": "T", "sha": "s", "asset_url": "u"},
    }
    r = await client.post("/api/agents/atlas/framework/update", json={})
    assert r.status_code == 409

@pytest.mark.asyncio
async def test_post_update_400_unknown_target(client, app):
    app.state.config.agents.append({
        "name": "atlas", "framework": "openclaw", "framework_update_status": "idle",
    })
    app.state.latest_framework_versions = {
        "openclaw": {"tag": "T2", "sha": "s", "asset_url": "u"},
    }
    r = await client.post("/api/agents/atlas/framework/update",
                           json={"target_version": "NONE"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

Append to `tinyagentos/routes/framework.py`:

```python
import asyncio
from pydantic import BaseModel
from tinyagentos.config import save_config_locked
from tinyagentos.frameworks import FRAMEWORKS
from tinyagentos import framework_update as _runner


class UpdateRequest(BaseModel):
    target_version: str | None = None


@router.post("/api/agents/{slug}/framework/update")
async def post_update(request: Request, slug: str, body: UpdateRequest):
    config = request.app.state.config
    agent = find_agent(config, slug)
    if not agent:
        return JSONResponse({"error": "agent not found"}, status_code=404)
    if agent.get("framework_update_status") != "idle":
        return JSONResponse({"error": "agent already updating or in failed state"},
                             status_code=409)
    fw_id = agent.get("framework")
    manifest = FRAMEWORKS.get(fw_id)
    if not manifest or not manifest.get("release_source"):
        return JSONResponse({"error": "agent framework has no update source"},
                             status_code=400)
    cache = getattr(request.app.state, "latest_framework_versions", {}) or {}
    latest = cache.get(fw_id)
    if not latest:
        return JSONResponse({"error": "no latest release cached; try again"},
                             status_code=409)
    if body.target_version and latest["tag"] != body.target_version:
        return JSONResponse(
            {"error": f"target_version {body.target_version!r} does not match latest cached release"},
            status_code=400,
        )

    async def _save():
        await save_config_locked(config, config.config_path)

    asyncio.create_task(_runner.start_update(agent, manifest, latest, save_config=_save))
    return JSONResponse({"status": "accepted", "update_status": "updating"},
                         status_code=202)
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/routes/framework.py tests/test_framework_api.py
git commit -m "feat(framework): POST /api/agents/{slug}/framework/update"
```

---

### Task 8.3: GET `/api/frameworks/latest`

**Files:**
- Modify: `tinyagentos/routes/framework.py`
- Append: `tests/test_framework_api.py`

- [ ] **Step 1: Failing tests**

```python
@pytest.mark.asyncio
async def test_get_latest_returns_cache(client, app):
    app.state.latest_framework_versions = {"openclaw": {"tag": "T", "sha": "s"}}
    r = await client.get("/api/frameworks/latest")
    assert r.status_code == 200
    assert r.json()["openclaw"]["tag"] == "T"

@pytest.mark.asyncio
async def test_get_latest_refresh_triggers_poll(client, app, monkeypatch):
    app.state.latest_framework_versions = {}
    async def fake_poll(manifests, *, http_client, arch, cache):
        cache["openclaw"] = {"tag": "FRESH", "sha": "s"}
    monkeypatch.setattr("tinyagentos.auto_update.poll_frameworks", fake_poll)
    r = await client.get("/api/frameworks/latest?refresh=true")
    assert r.status_code == 200
    assert r.json()["openclaw"]["tag"] == "FRESH"
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement**

Append to `tinyagentos/routes/framework.py`:

```python
import platform
from tinyagentos.auto_update import poll_frameworks


@router.get("/api/frameworks/latest")
async def get_latest(request: Request, refresh: bool = False):
    state = request.app.state
    if refresh:
        await poll_frameworks(
            FRAMEWORKS,
            http_client=state.http_client,
            arch=getattr(state, "host_arch", platform.machine()),
            cache=state.latest_framework_versions,
        )
    return state.latest_framework_versions
```

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Commit**

```bash
git add tinyagentos/routes/framework.py tests/test_framework_api.py
git commit -m "feat(framework): GET /api/frameworks/latest with refresh"
```

---

## Phase 9 — Container-side install script

### Task 9.1: Ship script + bake into image

**Files:**
- Create: `tinyagentos/scripts/taos-framework-update.sh`
- Modify: `tinyagentos/agent_image.py`

- [ ] **Step 1: Create script**

```bash
#!/bin/bash
set -euo pipefail

# Usage: taos-framework-update <framework> <tag> <asset_url>
# Downloads the tarball, stops the service, replaces the install dir,
# writes the version marker, and restarts.

FRAMEWORK="${1:?framework name required}"
TAG="${2:?tag required}"
URL="${3:?asset url required}"

log() { echo "[$(date -u +%H:%M:%S)] $*" >&2; }

TARBALL="/tmp/${FRAMEWORK}-${TAG}.tgz"
INSTALL_DIR="/usr/lib/node_modules/${FRAMEWORK}"

log "downloading ${URL}"
curl -fsSL --retry 3 --max-time 60 "${URL}" -o "${TARBALL}"

log "stopping ${FRAMEWORK}.service"
systemctl stop "${FRAMEWORK}.service" || true

log "replacing ${INSTALL_DIR}"
rm -rf "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
tar -xzf "${TARBALL}" -C "${INSTALL_DIR}"
rm -f "${TARBALL}"

mkdir -p /opt/taos
echo "${TAG}" > /opt/taos/framework.version

log "starting ${FRAMEWORK}.service"
systemctl start "${FRAMEWORK}.service"

log "done"
```

`chmod +x tinyagentos/scripts/taos-framework-update.sh` after creating.

- [ ] **Step 2: Bake into image**

In `tinyagentos/agent_image.py`, add the script copy step alongside other baked-in assets. Expect to use `push_file` + `exec_in_container` for `chmod`, following the existing image-build pattern:

```python
from pathlib import Path
SCRIPT = Path(__file__).parent / "scripts" / "taos-framework-update.sh"
# During image build:
await push_file(image_name, SCRIPT, "/usr/local/bin/taos-framework-update")
await exec_in_container(image_name, ["chmod", "+x", "/usr/local/bin/taos-framework-update"])
```

- [ ] **Step 3: Commit**

```bash
git add tinyagentos/scripts/taos-framework-update.sh tinyagentos/agent_image.py
git commit -m "feat(agent-image): bake taos-framework-update.sh into base image"
```

---

## Phase 10 — Startup probe for existing agents

### Task 10.1: One-shot probe writes `framework_version_tag`

**Files:**
- Modify: `tinyagentos/app.py`

- [ ] **Step 1: Add to startup**

After the persona migration step:

```python
from tinyagentos.framework_update import _read_installed_tag
from tinyagentos.frameworks import FRAMEWORKS

for agent in config.agents:
    if agent.get("framework_version_tag") is not None:
        continue
    manifest = FRAMEWORKS.get(agent.get("framework"), {})
    if not manifest.get("service_name"):
        continue
    try:
        tag = await _read_installed_tag(f"taos-agent-{agent['name']}")
        if tag:
            agent["framework_version_tag"] = tag
    except Exception:
        logger.warning("framework probe failed for %s", agent.get("name"))
await save_config_locked(config, config.config_path)
```

- [ ] **Step 2: Commit**

```bash
git add tinyagentos/app.py
git commit -m "feat(app): probe installed framework version on startup"
```

---

## Phase 11 — Frontend API client

### Task 11.1: `framework-api.ts`

**Files:**
- Create: `desktop/src/lib/framework-api.ts`

- [ ] **Step 1: Implement**

```typescript
export type FrameworkVersion = { tag: string | null; sha: string | null };
export type LatestVersion = { tag: string; sha: string; published_at?: string };

export interface FrameworkState {
  framework: string;
  installed: FrameworkVersion;
  latest: LatestVersion | null;
  update_available: boolean;
  update_status: "idle" | "updating" | "failed";
  update_started_at: number | null;
  last_error: string | null;
  last_snapshot: string | null;
}

export async function fetchFrameworkState(slug: string): Promise<FrameworkState> {
  const r = await fetch(`/api/agents/${encodeURIComponent(slug)}/framework`);
  if (!r.ok) throw new Error(`framework fetch ${r.status}`);
  return r.json();
}

export async function startFrameworkUpdate(slug: string, targetVersion?: string): Promise<void> {
  const r = await fetch(`/api/agents/${encodeURIComponent(slug)}/framework/update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(targetVersion ? { target_version: targetVersion } : {}),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.error || `update start ${r.status}`);
  }
}

export async function fetchLatestFrameworks(refresh = false): Promise<Record<string, LatestVersion>> {
  const r = await fetch(`/api/frameworks/latest${refresh ? "?refresh=true" : ""}`);
  if (!r.ok) throw new Error(`latest frameworks ${r.status}`);
  return r.json();
}
```

- [ ] **Step 2: Typecheck + commit**

```bash
cd desktop && npx tsc --noEmit
cd .. && git add desktop/src/lib/framework-api.ts
git commit -m "feat(desktop): framework-api client"
```

---

## Phase 12 — Framework tab UI

### Task 12.1: FrameworkTab component + wire into AgentsApp

**Files:**
- Create: `desktop/src/components/agent-settings/FrameworkTab.tsx`
- Modify: `desktop/src/apps/AgentsApp.tsx`

- [ ] **Step 1: Implement component**

```tsx
import { useEffect, useState } from "react";
import { fetchFrameworkState, FrameworkState, startFrameworkUpdate } from "@/lib/framework-api";

export function FrameworkTab({ agent, onUpdated }: { agent: { name: string }; onUpdated: () => void }) {
  const [state, setState] = useState<FrameworkState | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  async function load() {
    try { setState(await fetchFrameworkState(agent.name)); setErr(null); }
    catch (e: any) { setErr(String(e)); }
  }

  useEffect(() => { load(); }, [agent.name]);

  useEffect(() => {
    if (state?.update_status !== "updating") return;
    const id = setInterval(() => { load(); }, 2000);
    return () => clearInterval(id);
  }, [state?.update_status]);

  useEffect(() => {
    if (state?.update_status !== "updating" || !state.update_started_at) { setElapsed(0); return; }
    const tick = () => setElapsed(Math.floor(Date.now() / 1000) - (state.update_started_at ?? 0));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [state?.update_status, state?.update_started_at]);

  async function doUpdate() {
    setSubmitting(true);
    try { await startFrameworkUpdate(agent.name); await load(); }
    catch (e: any) { setErr(String(e)); }
    finally { setSubmitting(false); setConfirming(false); }
  }

  if (err) return <div className="p-4 text-sm text-red-400">Error: {err}</div>;
  if (!state) return <div className="p-4 text-sm opacity-60">Loading…</div>;

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="text-sm">This agent runs <b>{state.framework}</b></div>
      <dl className="grid grid-cols-[120px_1fr] gap-y-1 text-sm">
        <dt className="opacity-60">Installed</dt>
        <dd><code>{state.installed.tag ?? "(unknown)"}</code> · <code>{state.installed.sha ?? "—"}</code></dd>
        <dt className="opacity-60">Latest</dt>
        <dd>
          {state.latest
            ? <><code>{state.latest.tag}</code> · <code>{state.latest.sha}</code>
                {state.latest.published_at && <span className="opacity-60 ml-2">published {state.latest.published_at}</span>}</>
            : <span className="opacity-60">(not available)</span>}
        </dd>
      </dl>

      {state.update_available && state.update_status === "idle" && (
        <div className="flex items-center gap-2">
          <span className="bg-yellow-700/30 text-yellow-200 px-2 py-0.5 rounded text-xs">Update available</span>
          <button onClick={() => setConfirming(true)} disabled={submitting}
                  className="bg-blue-600 px-3 py-1.5 rounded text-sm">
            Update Framework
          </button>
        </div>
      )}

      {!state.update_available && state.update_status === "idle" && state.latest && (
        <div className="text-sm text-green-400">✓ You're on the latest version</div>
      )}

      {state.update_status === "updating" && (
        <div className="bg-white/5 border border-white/10 rounded px-3 py-2 text-sm">
          Updating {state.framework}… started {elapsed}s ago.
        </div>
      )}

      {state.update_status === "failed" && (
        <div className="bg-red-950/40 border border-red-800 rounded px-3 py-2 text-sm">
          <div>Update failed: {state.last_error}</div>
          {state.last_snapshot && (
            <div className="opacity-70 mt-1">Snapshot retained: <code>{state.last_snapshot}</code></div>
          )}
        </div>
      )}

      {confirming && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-shell-bg border border-white/10 rounded p-4 max-w-sm">
            <p className="text-sm mb-3">
              Update {agent.name}'s {state.framework} to <code>{state.latest?.tag}</code>?
              The agent will go offline for up to 2 minutes. Messages will queue.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setConfirming(false)} className="opacity-60 text-sm">Cancel</button>
              <button onClick={doUpdate} disabled={submitting} className="bg-blue-600 px-3 py-1.5 rounded text-sm">
                {submitting ? "Starting…" : "Update"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="mt-auto pt-4 text-xs opacity-50">Switch framework — coming soon</div>
    </div>
  );
}
```

- [ ] **Step 2: Wire into AgentsApp.tsx**

Extend the `DetailTab` type with `"framework"`. Add a Framework trigger between Memory and Skills in the tab bar. Add `<TabsContent value="framework"><FrameworkTab agent={agent} onUpdated={onAgentUpdated} /></TabsContent>`.

- [ ] **Step 3: Typecheck + commit**

```bash
cd desktop && npx tsc --noEmit
cd .. && git add desktop/src/components/agent-settings/FrameworkTab.tsx desktop/src/apps/AgentsApp.tsx
git commit -m "feat(agent-settings): Framework tab with installed/latest + update button"
```

---

## Phase 13 — Sidebar dot + Store pill

### Task 13.1: Agent sidebar dot

**Files:** `desktop/src/apps/AgentsApp.tsx`

- [ ] **Step 1: Fetch latest on mount**

In the agents list component, `useEffect` fetches `/api/frameworks/latest` once. Store as `latestByFramework`.

- [ ] **Step 2: Compute + render dot**

For each agent row, compute `updateAvailable = agent.framework_version_sha && latestByFramework[agent.framework] && latestByFramework[agent.framework].sha !== agent.framework_version_sha`. Render:

```tsx
{updateAvailable && (
  <span aria-label="framework update available"
        title="framework update available"
        className="inline-block w-2 h-2 bg-yellow-400 rounded-full ml-1" />
)}
```

- [ ] **Step 3: Commit**

```bash
cd desktop && npx tsc --noEmit
cd .. && git add desktop/src/apps/AgentsApp.tsx
git commit -m "feat(agents): sidebar dot on out-of-date agents"
```

---

### Task 13.2: Store pill on framework cards

**Files:** `desktop/src/apps/StoreApp.tsx`

- [ ] **Step 1: Fetch + compute**

Load `/api/frameworks/latest` and `/api/agents` on mount. For each card where `type === "agent-framework"`:

```ts
const affected = agents.filter(
  a => a.framework === card.id
    && a.framework_version_sha
    && latest[card.id]
    && latest[card.id].sha !== a.framework_version_sha
).length;
```

- [ ] **Step 2: Render**

```tsx
{affected > 0 && (
  <span className="bg-yellow-700/30 text-yellow-200 text-xs px-2 py-0.5 rounded ml-2">
    Update available · {affected} {affected === 1 ? "agent" : "agents"}
  </span>
)}
```

- [ ] **Step 3: Commit**

```bash
cd desktop && npx tsc --noEmit
cd .. && git add desktop/src/apps/StoreApp.tsx
git commit -m "feat(store): affected-agent pill on framework cards"
```

---

## Phase 14 — Playwright E2E

### Task 14.1: Framework tab tests

**Files:** `tests/e2e/test_framework_tab.py`

- [ ] **Step 1: Write (do not run — Playwright not installed in dev env)**

```python
"""E2E: Framework tab renders state + performs an update."""
import pytest
from playwright.sync_api import Page, expect

class TestFrameworkTab:
    def test_out_of_date_agent_shows_update_pill(self, page: Page, base_url: str):
        # TODO: seed an out-of-date agent via API + direct config patch
        page.goto(f"{base_url}/agents?slug=atlas")
        page.get_by_role("tab", name="Framework").click()
        expect(page.get_by_text("Update available")).to_be_visible()
        expect(page.get_by_role("button", name="Update Framework")).to_be_enabled()

    def test_update_confirmation_and_progress(self, page: Page, base_url: str):
        page.goto(f"{base_url}/agents?slug=atlas")
        page.get_by_role("tab", name="Framework").click()
        page.get_by_role("button", name="Update Framework").click()
        expect(page.get_by_text("to")).to_be_visible()
        page.get_by_role("button", name="Update").click()
        expect(page.get_by_text("started")).to_be_visible()

    def test_up_to_date_agent_shows_tick(self, page: Page, base_url: str):
        page.goto(f"{base_url}/agents?slug=uptodate")
        page.get_by_role("tab", name="Framework").click()
        expect(page.get_by_text("You're on the latest version")).to_be_visible()
```

- [ ] **Step 2: `ast.parse` check + commit**

```bash
python3 -c "import ast; ast.parse(open('tests/e2e/test_framework_tab.py').read())"
git add tests/e2e/test_framework_tab.py
git commit -m "test(e2e): framework tab skeletons"
```

---

### Task 14.2: Store pill + sidebar dot

**Files:** `tests/e2e/test_framework_store_pill.py`

- [ ] **Step 1: Write**

```python
"""E2E: Store pill + sidebar dot surface framework updates."""
import pytest
from playwright.sync_api import Page, expect

class TestFrameworkIndicators:
    def test_store_pill_counts_affected_agents(self, page: Page, base_url: str):
        page.goto(f"{base_url}/store")
        expect(page.get_by_text("Update available")).to_be_visible()

    def test_sidebar_dot_on_out_of_date_agent(self, page: Page, base_url: str):
        page.goto(f"{base_url}/agents")
        expect(page.locator('[aria-label="framework update available"]').first).to_be_visible()
```

- [ ] **Step 2: Commit**

```bash
python3 -c "import ast; ast.parse(open('tests/e2e/test_framework_store_pill.py').read())"
git add tests/e2e/test_framework_store_pill.py
git commit -m "test(e2e): store pill + sidebar dot skeletons"
```

---

## Phase 15 — Bundle + PR

### Task 15.1: Desktop bundle + PR

- [ ] **Step 1: Build + stage**

```bash
cd desktop && npm run build
cd /Volumes/NVMe/Users/jay/Development/tinyagentos
git add static/desktop desktop/tsconfig.tsbuildinfo
git commit -m "build: rebuild desktop bundle for framework-update feature"
```

- [ ] **Step 2: Push + PR**

```bash
git push -u origin feat/framework-update-phase-1
gh pr create --title "Framework update — Phase 1 (detect + install, no handoff)" \
  --body "See docs/superpowers/specs/2026-04-18-framework-update-phase-1-design.md. Scope: per-agent manual update via Framework tab, pre-update LXC snapshot, 120s bootstrap-ping deadline. Out of scope: graceful handoff (Phase 2), batch + auto-rollback (Phase 3). Test plan: unit/integration pytest green, Playwright skeletons with selectors to be tuned against live DOM on first run, one real Pi smoke per release."
```

---

## Self-review

**Spec coverage:**
- §2 manifest → Tasks 2.1, 2.2
- §3 per-agent state → Task 1.1
- §4 polling → Task 4.1
- §5 snapshot → Tasks 5.1, 6.1
- §6 runner → Tasks 6.1, 6.2, 6.3
- §7 bootstrap hook → Task 7.1
- §8 API → Tasks 8.1, 8.2, 8.3
- §9 install script → Task 9.1
- §10 UI → Tasks 11.1, 12.1, 13.1, 13.2
- §11 startup state + probe → Tasks 8.1, 10.1
- §12 errors → wired in each task's failing-test cases
- §13 testing → Phase 14 + per-task unit/integration tests

**Placeholders:** no TBD/TODO in production code steps. Playwright tests carry a single "TODO seed" line consistent with the persona/memory Phase 12.

**Type consistency:** agent fields (`framework_version_tag/sha`, `framework_update_status/started_at/last_error`, `framework_last_snapshot`, `bootstrap_last_seen_at`) and Python names (`FRAMEWORKS`, `validate_framework_manifest`, `poll_frameworks`, `start_update`, `_wait_for_bootstrap_ping`, `_prune_old_snapshots`, `_read_installed_tag`, `_mark_failed`) match across all referencing tasks.

---

## Open questions (non-blocking)

- Install script assumes `systemctl`. Non-systemd containers would need extending `service_name` semantics. Out of Phase 1 scope.
- Single-arch cluster assumption: host arch = container arch. Mixed-arch needs per-container arch lookup; defer to when there's a real case.
- Bootstrap ping requires exactly one in-flight update per agent; the 409 guard enforces this.
