# LXC Migration — Gitea Pi ⇆ Fedora Worker

**Goal:** install Gitea as an LXC service on the Orange Pi, move its container
to the Fedora worker, verify it still serves, then move it back.

This is the end-to-end validation for the store's LXC install path and the
incus cross-host migration feature.

## Pre-flight (one-time)

Both hosts need incus installed and reachable on the LAN, plus TLS trust
between them.

On **both** hosts:

```bash
incus --version   # must be present; any recent release is fine
```

On the **target** host (Fedora worker), configure incus to listen on the LAN
and set a trust password:

```bash
incus config set core.https_address :8443
incus config set core.trust_password '<temporary-trust-password>'
```

The trust password is consumed once per remote registration and cleared
after, so a short-lived value is fine.

## Procedure

### 1. Register the Fedora worker as an incus remote on the Pi

```bash
# on the Pi (jay@orangepi5-plus)
curl -X POST http://localhost:6969/api/cluster/remotes \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "fedora-worker",
    "url": "https://<fedora-worker-host>:8443",
    "trust_password": "<temporary-trust-password>"
  }'

# verify
curl http://localhost:6969/api/cluster/remotes
```

### 2. Install Gitea via the LXC path

Use the store UI or POST directly:

```bash
curl -X POST http://localhost:6969/api/store/install-v2 \
  -H 'Content-Type: application/json' \
  -b 'taos_session=<your-session-cookie>' \
  -d '{
    "app_id": "gitea-lxc",
    "admin_password": "<pick-a-strong-password>"
  }'
```

Wait for the response — install takes 2-3 minutes (incus launch + apt
install + Gitea download). Response includes `host_port` used for the
proxy device.

Verify Gitea responds:

```bash
curl -I http://localhost:<host_port>/
# expect: HTTP/1.1 200 OK
```

Log in via the browser at `http://<pi-host>:<host_port>/` using your taOS
username and the admin password from step 2.

### 3. Migrate container to the Fedora worker

```bash
curl -X POST http://localhost:6969/api/cluster/migrate \
  -H 'Content-Type: application/json' \
  -d '{
    "container": "taos-svc-gitea-lxc",
    "target_remote": "fedora-worker",
    "keep_source": false,
    "stateless": true
  }'
```

This stops the container on the Pi, copies it across the LAN, and starts it
on the Fedora worker. Expect a few minutes for the copy.

Verify it's running on the target:

```bash
# on the Fedora worker
incus list taos-svc-gitea-lxc
# Status: RUNNING
```

And that Gitea still serves. The proxy device follows the container, so the
same port works on the new host:

```bash
curl -I http://<fedora-worker-host>:<host_port>/
# expect: HTTP/1.1 200 OK
```

Log in and spot-check that your user account and any repos are intact —
state lives in the container's `/home/git/` and moved with it.

### 4. Migrate back to the Pi

Before moving back, add the Pi as a remote on the Fedora worker (mirror of
step 1 but in reverse). Then from the Fedora worker:

```bash
curl -X POST http://<fedora-worker-host>:6969/api/cluster/migrate \
  -H 'Content-Type: application/json' \
  -d '{
    "container": "taos-svc-gitea-lxc",
    "target_remote": "orangepi",
    "keep_source": false,
    "stateless": true
  }'
```

Verify Gitea responds on the Pi again, and the admin user still works.

## Recovery

If a migration fails mid-way:

- The `migrate_container` helper restarts the source container automatically
  if the copy/move step failed after the stop.
- If the target has a half-copied container, `incus delete <remote>:<name>
  --force` cleans it up.
- A pre-stop snapshot is created best-effort on the source; `incus snapshot
  restore <name> pre-migrate-<ts>` rolls it back if needed.

## What this proves

- The LXC install path works end-to-end (container creation → Gitea install →
  admin seeding → proxy device → real HTTP traffic).
- `incus copy`/`incus move` across trusted remotes preserves all container
  state (rootfs, config, installed packages, SQLite DB).
- Proxy devices survive the move, so the same user-facing URL stays valid
  after a host change.
