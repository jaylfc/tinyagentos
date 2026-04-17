#!/usr/bin/env bash
# install.sh — openclaw agent runtime installer
# Runs once inside a fresh Debian bookworm LXC container.
# Idempotent: safe to re-run on an already-provisioned container.
#
# Pinned to jaylfc/openclaw at upstream main (SHA: be7a415eb096)
# Fork tracks upstream main; taos-fork branch carries the bridge patch.
set -euo pipefail

echo "[openclaw] installing Node 22.x (NodeSource) + openclaw from jaylfc fork"

# ---------------------------------------------------------------------------
# 1. Node 22.14+ via NodeSource (Debian bookworm default is Node 18, too old).
# ---------------------------------------------------------------------------
if ! command -v node >/dev/null 2>&1 || [ "$(node -v | sed 's/^v//; s/\..*//')" -lt 22 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends nodejs
fi

# ---------------------------------------------------------------------------
# 2. openclaw from our fork (taos-fork branch).
# Fork baseline tracks upstream main; the taos-fork branch adds the bridge patch.
# ---------------------------------------------------------------------------
npm install -g github:jaylfc/openclaw#taos-fork

# ---------------------------------------------------------------------------
# 3. Data dirs + .openclaw mount under /root (agent-home bind mount).
# openclaw.json is written by the deployer, not here. We only ensure the dir.
# ---------------------------------------------------------------------------
mkdir -p /root/.openclaw
chmod 700 /root/.openclaw

# ---------------------------------------------------------------------------
# 4. systemd unit for the gateway.
# ---------------------------------------------------------------------------
cat > /etc/systemd/system/openclaw.service <<'UNIT'
[Unit]
Description=openclaw gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=-/root/.openclaw/env
ExecStart=/usr/bin/openclaw gateway
Restart=on-failure
RestartSec=3
WorkingDirectory=/root

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now openclaw.service

# ---------------------------------------------------------------------------
# 5. Wait for openclaw to be ready (health RPC).
# ---------------------------------------------------------------------------
for i in $(seq 1 30); do
  if openclaw health --timeout 2000 >/dev/null 2>&1; then
    echo "[openclaw] ready"
    break
  fi
  sleep 1
  if [ "$i" -eq 30 ]; then
    echo "[openclaw] FAILED to become ready in 30s"
    journalctl -u openclaw.service --no-pager -n 50 || true
    exit 1
  fi
done

echo "[openclaw] install complete"
