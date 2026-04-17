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
#    Also ensure git is present — npm's github: shorthand uses git to clone.
# ---------------------------------------------------------------------------
if ! command -v node >/dev/null 2>&1 || [ "$(node -v | sed 's/^v//; s/\..*//')" -lt 22 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends nodejs
fi
if ! command -v git >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends git
fi

# ---------------------------------------------------------------------------
# 2. openclaw from our fork (taos-fork branch).
# Fork baseline tracks upstream main; the taos-fork branch adds the bridge patch.
#
# Use npm's github: shorthand (NOT a tarball URL) so npm's prepare
# script fires. The prepare script detects it is outside a git work tree
# (i.e. an npm global install) and runs `pnpm build:docker` in the
# destination, producing dist/entry.js at install time.
#
# Tarball URLs skip the prepare lifecycle entirely — that is why prebuilt
# dist/ kept landing as incomplete and crashing openclaw.mjs:178.
#
# corepack is bundled with Node 22 (no apt install needed). The pnpm
# build step adds ~2-3 minutes on arm64 Pi hardware.
# ---------------------------------------------------------------------------
corepack enable
corepack prepare pnpm@latest --activate
npm install -g github:jaylfc/openclaw#taos-fork

# ------------------------------------------------------------------
# 2a. Bootstrap config + env for the openclaw bridge. Written from env
# vars the deployer set via `incus config set environment.*`.
# These live inside the container rootfs (not on the host) so they
# travel with snapshot-based archives cleanly.
# ------------------------------------------------------------------

mkdir -p /root/.openclaw
chmod 700 /root/.openclaw

# Resolve values or fall back to safe defaults for dev/test.
: "${TAOS_AGENT_NAME:=unknown}"
: "${TAOS_MODEL:=}"
: "${OPENAI_BASE_URL:=http://127.0.0.1:4000/v1}"
: "${OPENAI_API_KEY:=}"
: "${TAOS_BRIDGE_URL:=http://127.0.0.1:6969}"
: "${TAOS_LOCAL_TOKEN:=}"

cat > /root/.openclaw/openclaw.json <<JSON_EOF
{
  "gateway": { "bind": "loopback", "port": 18789, "auth": { "mode": "token" } },
  "channels": {},
  "models": {
    "providers": [
      {
        "id": "taos",
        "api": "openai-completions",
        "baseUrl": "${OPENAI_BASE_URL}",
        "apiKey": "${OPENAI_API_KEY}",
        "default_model": "${TAOS_MODEL}"
      }
    ]
  }
}
JSON_EOF
chmod 600 /root/.openclaw/openclaw.json

cat > /root/.openclaw/env <<ENV_EOF
TAOS_AGENT_NAME=${TAOS_AGENT_NAME}
TAOS_BRIDGE_URL=${TAOS_BRIDGE_URL}
TAOS_LOCAL_TOKEN=${TAOS_LOCAL_TOKEN}
TAOS_MODEL=${TAOS_MODEL}
OPENAI_BASE_URL=${OPENAI_BASE_URL}
OPENAI_API_KEY=${OPENAI_API_KEY}
ENV_EOF
chmod 600 /root/.openclaw/env

# ===== BEGIN recycle-bin install (Layer 1) — see app-catalog/_common/scripts/recycle-bin-install.sh =====
# Install taOS recycle-bin (Layer 1). Shared across agent frameworks.
echo "[recycle-bin] installing trash-cli and shadow rm wrapper"

# 1. trash-cli
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends trash-cli

# 2. Point trash-cli at /var/recycle-bin (XDG_DATA_HOME/Trash convention)
mkdir -p /var/recycle-bin/files /var/recycle-bin/info
chmod 1777 /var/recycle-bin /var/recycle-bin/files /var/recycle-bin/info

# Global environment so all shells (including systemd, sudo) pick it up.
cat > /etc/profile.d/taos-recycle-bin.sh <<'EOF'
# Point trash-cli at /var/recycle-bin (system-wide taOS recycle bin).
export XDG_DATA_HOME=/var
EOF
chmod 644 /etc/profile.d/taos-recycle-bin.sh

# 3. Shadow /usr/local/bin/rm
cat > /usr/local/bin/rm <<'EOF'
#!/usr/bin/env bash
# taOS shadow rm — soft-delete via trash-put unless TAOS_TRASH_DISABLE=1 set.
# Invoke /usr/bin/rm directly for permanent delete without this shadow.
set -euo pipefail
if [ "${TAOS_TRASH_DISABLE:-0}" = "1" ]; then
  exec /usr/bin/rm "$@"
fi
# Pass through if no args or only flags (trash-put rejects; /usr/bin/rm handles usage errors).
HAS_PATHS=0
for a in "$@"; do
  case "$a" in
    -*) ;;
    *)  HAS_PATHS=1; break ;;
  esac
done
if [ "$HAS_PATHS" = "0" ]; then
  exec /usr/bin/rm "$@"
fi
# Route only the path operands through trash-put. Flags (-r, -f, etc.) are ignored
# because trash-put's semantics differ; but -r recursion is default for directories
# and -f suppresses errors by our choice.
for arg in "$@"; do
  case "$arg" in
    -*) ;;
    *)  trash-put -- "$arg" 2>/dev/null || /usr/bin/rm -f -- "$arg" ;;
  esac
done
EOF
chmod 755 /usr/local/bin/rm

# 4. 30-day retention sweep: /usr/local/bin/taos-recycle-sweep + systemd timer
cat > /usr/local/bin/taos-recycle-sweep <<'EOF'
#!/usr/bin/env bash
# Deletes items from /var/recycle-bin older than 30 days.
# Safe to run daily; idempotent.
set -euo pipefail
find /var/recycle-bin/files -mindepth 1 -mtime +30 -print0 2>/dev/null \
  | xargs -0 -r /usr/bin/rm -rf
find /var/recycle-bin/info -mindepth 1 -mtime +30 -type f -name '*.trashinfo' \
  -delete 2>/dev/null || true
EOF
chmod 755 /usr/local/bin/taos-recycle-sweep

cat > /etc/systemd/system/tinyagentos-recycle-sweep.service <<'EOF'
[Unit]
Description=taOS recycle-bin 30-day retention sweep

[Service]
Type=oneshot
ExecStart=/usr/local/bin/taos-recycle-sweep
EOF

cat > /etc/systemd/system/tinyagentos-recycle-sweep.timer <<'EOF'
[Unit]
Description=Daily taOS recycle-bin retention sweep

[Timer]
OnBootSec=30min
OnUnitActiveSec=24h
Persistent=true
Unit=tinyagentos-recycle-sweep.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now tinyagentos-recycle-sweep.timer

echo "[recycle-bin] ready; /usr/local/bin/rm now soft-deletes to /var/recycle-bin"
# ===== END recycle-bin install =====

# ---------------------------------------------------------------------------
# 3. systemd unit for the gateway.
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
# 4. Wait for openclaw to be ready (health RPC).
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
