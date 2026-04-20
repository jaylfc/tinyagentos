# Framework update — Phase 1 (detect + install, no handoff) — design spec

**Date:** 2026-04-18
**Status:** Proposed
**Phase:** 1 of 3. Phase 2 (graceful handoff with pause/resume note) and Phase 3 (batch updates, auto-rollback) are separate specs, not scoped here.

## Summary

Adds per-agent detection and manual installation of framework updates. A new **Framework tab** in Agent Settings shows the installed vs latest version of an agent's framework (openclaw today) and a single-button update that: takes an LXC snapshot for safety, stops the framework service inside the container, swaps in the new tarball, and restarts the service. The bridge's first bootstrap call after restart is the "agent is back" signal, bounded by a 120-second timeout. Incoming messages queue via the existing channel hub so no user traffic is lost. Framework manifest carries enough metadata (`release_source`, `install_script`, `service_name`, `release_asset_pattern`) that Hermes and future frameworks plug in as manifest entries without new runner code.

## Scope

**In:**
- Per-agent manual update flow via Agent Settings → new Framework tab.
- Generic framework manifest — one implementation today (openclaw), contract accepts more.
- Hourly GitHub Releases poll piggybacking on `auto_update.py`.
- Pre-update LXC snapshot with 3-deep retention (manual rollback only).
- Container-side install script baked into the base image.
- Store pill indicating number of out-of-date agents per framework.
- Sidebar dot on agent rows when an update is available for that agent.
- 120s failure timeout surfacing a red banner with snapshot name + Logs link.

**Out:**
- Graceful agent pause + handoff note + resume (Phase 2 spec).
- Batch "update all agents on openclaw" flow (Phase 3 spec).
- Auto-rollback on failure (Phase 3 spec).
- Framework swap UX (a separate later spec — the Framework tab reserves space for it).
- Scheduled auto-updates (always manual in Phase 1).
- Dashboard-wide "N updates pending" summary.
- Pinning to a specific version via UI (API accepts `target_version` but the tab only offers "Update to latest").

## Framework manifest

Extend `tinyagentos/frameworks.py` (the existing framework registry) with per-framework update metadata:

```python
FRAMEWORKS = {
    "openclaw": {
        "id": "openclaw",
        "name": "OpenClaw",
        # ...existing fields preserved...
        "release_source": "github:jaylfc/openclaw",
        "release_asset_pattern": "openclaw-taos-fork-linux-{arch}.tgz",
        "install_script": "/usr/local/bin/taos-framework-update",
        "service_name": "openclaw",
    },
}
```

Four new fields:

| Field | Purpose |
|---|---|
| `release_source` | Target for the poller. `github:<owner>/<repo>` for now; other schemes later. |
| `release_asset_pattern` | Template (`{arch}` substituted on the host — `x86_64` or `aarch64`) for the asset to download. Resolved against the release's assets list; missing asset fails fast. |
| `install_script` | Path of the script invoked via `exec_in_container` inside the agent's container. |
| `service_name` | Passed to `systemctl stop/start` by the install script. |

Startup-time validation: an entry missing any of the four is logged and the framework is treated as "not updatable" — existing agents on that framework still run, just can't receive updates.

## Per-agent state

Five new fields on the agent dict stored in `config.yaml` (following the pattern from the persona/memory spec's `normalize_agent` backfill):

| Field | Type | Default | Purpose |
|---|---|---|---|
| `framework_version_tag` | str \| null | `null` | e.g. `"20260418T133712"`. Set at first deploy; updated after each successful install. |
| `framework_version_sha` | str \| null | `null` | 7-char short SHA (`"9bab2e3"`). Source of truth for the out-of-date comparison. |
| `framework_update_status` | enum `"idle" \| "updating" \| "failed"` | `"idle"` | State machine. |
| `framework_update_started_at` | int \| null | `null` | UTC seconds — used to compute the 120s deadline. |
| `framework_update_last_error` | str \| null | `null` | stderr excerpt / timeout message, surfaced in the failure banner. Cleared on next successful update. |
| `framework_last_snapshot` | str \| null | `null` | Name of the most recent pre-update snapshot taken for this agent, e.g. `"pre-framework-update-20260419T100000-2026-04-18T22-45-12"`. Set every time the runner snapshots. Never cleared automatically (accepts that it may reference a snapshot that has since been pruned — the name still tells the operator what was attempted). |

Plus one field consumed (not owned) by the updater:

| Field | Set by | Purpose |
|---|---|---|
| `bootstrap_last_seen_at` | `routes/openclaw.py:/api/openclaw/bootstrap` handler | UTC seconds. Timestamp of the most recent bootstrap call from the bridge. Used by the updater as the "bridge reconnected" signal. |

Migration for existing agents: `framework_update_status` defaults to `"idle"` via `normalize_agent`. `framework_version_tag`/`sha` backfill via a one-time probe — the base image build writes `/opt/taos/framework.version` when it unpacks openclaw, and the poll service on startup runs an `exec_in_container` read once per agent to populate the fields.

## Version polling service

Extends `tinyagentos/auto_update.py`'s existing hourly tick. Same loop, added block:

```python
for fw_id, manifest in FRAMEWORKS.items():
    if not manifest.get("release_source"):
        continue
    try:
        cached = await _fetch_latest_release(manifest, http_client)
        app.state.latest_framework_versions[fw_id] = cached
    except Exception:
        logger.warning("latest-release poll for %s failed; keeping last good", fw_id)
```

The cache on `app.state.latest_framework_versions` is a `dict[str, {tag, sha, short_sha, published_at, asset_url}]`. Failures preserve the last good entry rather than clearing — stale data is better than no data.

Manual refresh: a **"Check now"** link on the Framework tab hits `GET /api/frameworks/latest?refresh=true` which forces one poll cycle bypass-cache. Used when the user has just pushed a release and wants it picked up immediately.

## Pre-update snapshot

Before `systemctl stop`, the runner calls the existing `tinyagentos/containers.py:snapshot_create` helper with a deterministic name:

```
pre-framework-update-<new-tag>-<utc-compact>

example:
pre-framework-update-20260419T100000-2026-04-18T22-45-12
```

Retention: after creating the snapshot, the runner lists all `pre-framework-update-*` snapshots for the container and prunes any beyond the 3 most recent (by snapshot creation time). Snapshot deletion is via `snapshot_delete` — add the helper to `containers.py` if it doesn't exist.

Phase 1 does **not** auto-restore. If the update fails, the snapshot name is printed in the failure banner alongside a note *"Contact Jay / run `incus restore` to roll back"*. Phase 3 adds the one-click rollback button and decision logic.

Cost: ~2-5s extra per update on btrfs/ZFS (zero-copy); longer on dir-backed pools. Inside the 120s budget regardless.

## Update runner

New module `tinyagentos/framework_update.py`. One module owns the orchestration; modelled on the existing `deploy_tasks` pattern where the HTTP endpoint kicks off a background asyncio Task and the client polls status.

```python
async def start_update(agent: dict, manifest: dict, latest: dict, app_state) -> None:
    """Idempotent-on-retry background update runner. Caller must not
    double-invoke for the same agent — the API endpoint guards with 409."""
    started_at = int(time.time())
    agent["framework_update_status"] = "updating"
    agent["framework_update_started_at"] = started_at
    agent["framework_update_last_error"] = None
    await save_config_locked(config, config.config_path)

    container = f"taos-agent-{agent['name']}"

    # Snapshot + prune. Snapshot failure aborts before touching the service.
    snap = f"pre-framework-update-{latest['tag']}-{_iso_utc_compact()}"
    try:
        await snapshot_create(container, snap)
        agent["framework_last_snapshot"] = snap
        await save_config_locked(config, config.config_path)
        await _prune_old_snapshots(container, keep=3)
    except Exception as e:
        return await _mark_failed(agent, f"snapshot failed: {e}")

    # Run install script inside the container.
    try:
        rc, stderr = await exec_in_container(container, [
            manifest["install_script"],
            manifest["id"],
            latest["tag"],
            latest["asset_url"],
        ], timeout=120)
        if rc != 0:
            return await _mark_failed(agent, f"install script rc={rc}: {stderr[:500]}", snapshot=snap)
    except asyncio.TimeoutError:
        return await _mark_failed(agent, "install script timed out", snapshot=snap)

    # Wait for the bridge to call bootstrap, bounded by the 120s window from
    # started_at (NOT from now — the script itself may have taken most of it).
    deadline = started_at + 120
    if not await _wait_for_bootstrap_ping(agent, deadline):
        return await _mark_failed(agent, "bridge did not reconnect within 120s", snapshot=snap)

    # Success: read the version marker inside the container to verify.
    installed_tag = await _read_installed_tag(container)
    if installed_tag != latest["tag"]:
        return await _mark_failed(agent, f"version mismatch: installed={installed_tag} expected={latest['tag']}", snapshot=snap)

    agent["framework_version_tag"] = installed_tag
    agent["framework_version_sha"] = latest["sha"]
    agent["framework_update_status"] = "idle"
    agent["framework_update_started_at"] = None
    await save_config_locked(config, config.config_path)
```

`_wait_for_bootstrap_ping` polls `agent["bootstrap_last_seen_at"]` every 500ms and returns `True` the first time it exceeds `started_at`. `_read_installed_tag` runs `exec_in_container(container, ["cat", "/opt/taos/framework.version"])`.

The "bridge reconnected" signal is **not a filesystem poll** — it's a timestamp bumped on the agent record every time `/api/openclaw/bootstrap` is called. One two-line addition to that existing handler:

```python
# routes/openclaw.py — inside the bootstrap endpoint, after loading the agent
agent["bootstrap_last_seen_at"] = int(time.time())
await save_config_locked(config, config.config_path)
```

Why: bootstrap is the bridge's *first* call on startup. Using it as the ready signal means no new heartbeat plumbing inside the container.

## Container-side install script

New file `/usr/local/bin/taos-framework-update`, baked into the base image by `tinyagentos/agent_image.py`:

```bash
#!/bin/bash
set -euo pipefail

# Usage: taos-framework-update <framework> <tag> <asset_url>
# Downloads the tarball, stops the service, replaces the install dir,
# writes the version marker, and restarts. Exit non-zero on any failure;
# taOS host-side uses the exit code + the 120s bootstrap-ping deadline
# as the success gate.

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

Re-runnable: the same `(framework, tag, url)` tuple produces the same result whether or not a previous run partially completed. This matters when we add retry in Phase 3.

## Backend API

New router `tinyagentos/routes/framework.py`, registered in `app.py` alongside the other routers.

### `GET /api/agents/{slug}/framework`

Returns the Framework tab's full state:

```json
{
  "framework": "openclaw",
  "installed": { "tag": "20260418T133712", "sha": "9bab2e3" },
  "latest":    { "tag": "20260419T100000", "sha": "abc1234",
                 "published_at": "2026-04-19T10:00:00Z" },
  "update_available": true,
  "update_status": "idle",
  "update_started_at": null,
  "last_error": null,
  "last_snapshot": "pre-framework-update-20260418T133712-..."
}
```

404 if the agent isn't found. If the agent's framework has no `release_source`, `latest` is `null` and `update_available` is `false`.

### `POST /api/agents/{slug}/framework/update`

Body (optional):

```json
{ "target_version": "20260419T100000" }
```

If `target_version` is omitted, the endpoint uses `app.state.latest_framework_versions[framework].tag`. If `target_version` is supplied but doesn't match a known release, returns **400**.

Responses:
- **202** + initial state dict when the background task is kicked off.
- **409** if `framework_update_status != "idle"`.
- **409** if the agent has no container (failed deploy, archived, etc.).
- **400** if the agent has no `framework` field or the manifest entry lacks `release_source`.

### `GET /api/frameworks/latest`

Query: `?refresh=true` forces one poll bypass-cache.

Returns the full `latest_framework_versions` cache. Consumed by the Store pill and the Framework tab.

## GitHub Releases parsing

openclaw's release naming (`"20260418T133712"` for the tag, with `"· 9bab2e3"` appearing in the **release name**, not the tag) requires careful field choice:

```python
release = await github.get(f"/repos/{owner}/{repo}/releases/latest")
full_sha = release["target_commitish"]                 # full 40-char SHA
short_sha = full_sha[:7]                                # "9bab2e3"
tag = release["tag_name"]                               # "20260418T133712"

# Asset pattern resolved host-side with the agent's container arch.
arch = await _agent_arch(container)                     # "x86_64" | "aarch64"
expected_name = manifest["release_asset_pattern"].format(arch=arch)
asset = next((a for a in release["assets"] if a["name"] == expected_name), None)
if asset is None:
    raise ReleaseAssetNotFoundError(expected_name)
asset_url = asset["browser_download_url"]
```

Host-side arch resolution (via `uname -m` inside the container, cached per-agent) means the URL is validated against the real asset list before kick-off — a missing asset fails before we even try `exec_in_container`.

## UI surfaces

### Agent Settings — new Framework tab

Inserted between Memory and Skills. Final tab order: **Logs, Persona, Memory, Framework, Skills, Messages.**

Content:

- Header: *"This agent runs **OpenClaw**"*
- Installed row: `20260418T133712` · `9bab2e3`
- Latest row: `20260419T100000` · `abc1234` *(published 2h ago)* — or a green ✓ "You're on the latest version"
- Yellow **Update available** pill when out of date
- **Update Framework** button — disabled while `update_status !== "idle"`
- Confirmation dialog on click: *"Update Atlas's OpenClaw to `20260419T100000`? Atlas will go offline for up to 2 minutes. Messages will queue and be delivered when it's back."*
- During update: grey banner *"Updating OpenClaw… started 24s ago."* with live elapsed counter so the user knows it's not frozen.
- On failure: red banner with the snapshot name and a **Check Logs** button that jumps to the Logs tab filtered to recent framework-update events.
- Placeholder at bottom: *"Switch framework — coming soon"* so the tab's broader purpose is visible.

### Agents list (sidebar)

Tiny yellow dot on the agent row when that agent's `update_available` is true. Tooltip: `"openclaw update available"`. No click action — the user is expected to click the row and navigate to the Framework tab themselves.

### Store — OpenClaw card

Informational pill: *"Update available • 3 agents"* where `3` is the count of deployed agents running openclaw with `update_available=true`. No action button in Phase 1; click on the pill takes the user to the first affected agent's Framework tab.

## Error handling

| Failure | Behaviour |
|---|---|
| GitHub API rate-limited (HTTP 403) or 5xx during poll | Keep last-good cache entry; log warning. UI shows stale values until the next successful poll. No user-facing error. |
| `exec_in_container` returns non-zero exit | `status=failed`, stderr[:500] captured in `framework_update_last_error`, red banner references it. |
| Bridge fails to call bootstrap within 120s | `status=failed` with *"bridge did not reconnect within 120s"* in `framework_update_last_error`. Snapshot retained. |
| User clicks Update while already updating | `409 Conflict`. |
| User supplies unknown `target_version` | `400 Bad Request`. |
| Agent container doesn't exist | `409 Conflict` with *"no container to update"*. |
| Snapshot creation fails (disk full, pool offline) | Abort before `stop` runs; revert `status` to idle; surface the snapshot error in `last_error`. Install not attempted. |
| Install script fails after snapshot but before service restart | `status=failed`; snapshot retained; user can manually `incus restore`. |
| Post-install version marker mismatch | `status=failed` — treats the install as broken even if exit code was zero. Snapshot retained. |
| Agent record missing `framework` field | `400` with *"agent has no framework recorded"* (edge case for legacy records). |

## Testing

### Unit

- `_parse_latest_release`: tag, full_sha, short_sha, asset_url correct for both `x86_64` and `aarch64` arch substitution. Missing asset raises `ReleaseAssetNotFoundError`.
- `_wait_for_bootstrap_ping`: returns promptly when the ping arrives early; respects the 120s deadline on timeout.
- `_prune_old_snapshots`: given 5 matching snapshots, keeps the 3 most recent; unrelated snapshots (other prefixes) untouched.
- Version comparison: `update_available` is driven by `installed.sha != latest.sha` (tag ignored — SHA is the truth).
- Manifest validation at startup rejects frameworks missing any of the four new required fields.
- API: `409` on double-update, `400` on bad target_version, `404` on unknown agent, `200` shape stable.

### Integration

- End-to-end update with mocked `exec_in_container` + simulated bootstrap ping: agent record transitions `idle → updating → idle`, snapshot created, 4th concurrent update attempt for a different agent gets its own snapshot and the third agent prunes.
- Failure path: install script returns non-zero → `status=failed`, snapshot retained, `last_error` accurate.
- Timeout path: no bootstrap ping within 120s → `status=failed`.
- Snapshot-failure-before-install path: runner aborts, status reverts to idle, install never attempted.

### Playwright E2E (Python, `tests/e2e/`)

- Framework tab renders installed + latest rows, click update → confirmation dialog → grey banner → completion clears the pill and the sidebar dot.
- Sidebar dot visible when `update_available`, gone after successful update.
- Store pill shows correct count of affected agents and updates when that count changes.
- Failure path (backend mocked to return `status=failed`) → red banner visible with snapshot name.

### Manual smoke

One documented Pi run against a real openclaw release, end-to-end. Verified: bridge reconnects, `/opt/taos/framework.version` shows new tag, trace events resume on the next turn.

## Out of scope — future phases

### Phase 2: graceful handoff
- New `POST /api/agents/{slug}/pause-for-update` that injects a handoff prompt through the bridge, writes a taosmd note titled `pre-update-handoff-<timestamp>`, waits for the agent's final reply.
- Post-update resume prompt that references the note id.
- Mid-tool-call pause semantics (pause is only delivered between turns, never mid-tool-sequence).

### Phase 3: batch + rollback
- `POST /api/frameworks/{id}/update-all` that processes agents serially, halting on first failure.
- Auto-rollback on failure: `incus restore <container> <snapshot>` plus bridge health-ping to verify the restored version works.
- UI: single Store-level "Update all" button, dashboard-wide summary.
- Rollback button per agent on the Framework tab (enabled when `last_snapshot` exists).

### Separate: framework swap
- Same Framework tab hosts a future "Change framework" flow (openclaw → Hermes etc.). Uses the same manifest but cycles through deploy/teardown rather than update. Tracked as its own spec.
