#!/usr/bin/env bash
# install.sh — openclaw agent runtime installer
# Runs once inside a fresh Debian bookworm LXC container.
# Idempotent: safe to re-run on an already-provisioned container.
#
# Installs openclaw from prebuilt tarballs published by jaylfc/openclaw taos-fork CI.
# The fork's .github/workflows/release.yml builds per-arch tarballs on every push.
set -euo pipefail

echo "[openclaw] installing Node 22.x (NodeSource) + openclaw prebuilt from GitHub Releases"

# ---------------------------------------------------------------------------
# 1. Node 22.14+ via NodeSource (Debian bookworm default is Node 18, too old).
#    Also ensure:
#    - 'file' is present — used to sanity-check the downloaded tarball.
#    - 'git' is present — openclaw's transitive dep libsignal
#      (@whiskeysockets/baileys -> libsignal@git+https://github.com/...)
#      is a git-URL dependency and npm needs git to fetch it at install time.
# ---------------------------------------------------------------------------
if ! command -v node >/dev/null 2>&1 || [ "$(node -v | sed 's/^v//; s/\..*//')" -lt 22 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends nodejs
fi
if ! command -v file >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends file
fi
if ! command -v git >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends git
fi

# ----------------------------------------------------------------------
# 2. Install openclaw from a prebuilt tarball published by the fork's CI.
# This avoids any build-at-deploy time. The fork's GitHub Actions
# workflow .github/workflows/release.yml builds a fresh tarball per
# architecture on every push to taos-fork and publishes them as assets
# on the "rolling" Release. We always grab the latest.
#
# If GitHub is unreachable we FAIL — there is no build fallback. Build
# at deploy time was tried and is brittle (workspace deps, partial
# artefacts, slow on arm64); the right fix is to make the prebuilt path
# reliable, not to paper over its absence.
# ----------------------------------------------------------------------

# Architecture detection
ARCH=$(uname -m)
case "$ARCH" in
  aarch64|arm64) NPM_ARCH=arm64 ;;
  x86_64|amd64)  NPM_ARCH=x64 ;;
  *)
    echo "[openclaw] FATAL: unsupported architecture $ARCH"
    echo "[openclaw] supported: aarch64, x86_64"
    echo "[openclaw] open an issue at github.com/jaylfc/openclaw if you need another arch."
    exit 1
    ;;
esac

TARBALL_URL="https://github.com/jaylfc/openclaw/releases/latest/download/openclaw-taos-fork-linux-${NPM_ARCH}.tgz"
TARBALL_DEST="/tmp/openclaw-taos-fork-${NPM_ARCH}.tgz"

echo "[openclaw] downloading prebuilt tarball for ${NPM_ARCH} from GitHub Releases"
if ! curl -fsSL --max-time 120 -o "$TARBALL_DEST" "$TARBALL_URL"; then
  echo "[openclaw] FATAL: cannot download $TARBALL_URL"
  echo "[openclaw] check network connectivity to github.com from inside this container."
  echo "[openclaw] cf. docs/runbooks/openclaw-install-troubleshooting.md"
  exit 1
fi

# Sanity check the file we got
if ! [ -s "$TARBALL_DEST" ]; then
  echo "[openclaw] FATAL: downloaded tarball is empty"
  exit 1
fi
file "$TARBALL_DEST" | grep -qE "gzip|compressed" || {
  echo "[openclaw] FATAL: downloaded file is not a gzipped tarball:"
  file "$TARBALL_DEST"
  head -c 500 "$TARBALL_DEST"
  exit 1
}

# Install from the local file (no network re-fetch, no build).
# --ignore-scripts: the tarball already has dist/ built by CI; we must NOT
# run the prepare script because it tries to spawn git (for hook setup) and
# falls back to pnpm build:docker — both of which are wrong and unnecessary
# when installing a prebuilt tarball.
echo "[openclaw] installing $TARBALL_DEST"
npm install -g --unsafe-perm --ignore-scripts "$TARBALL_DEST"

# Cleanup the downloaded tarball — keeps container small
rm -f "$TARBALL_DEST"

# Verify entry exists
if [ ! -f /usr/lib/node_modules/openclaw/dist/entry.js ] && [ ! -f /usr/lib/node_modules/openclaw/dist/entry.mjs ]; then
  echo "[openclaw] FATAL: install completed but dist/entry.{js,mjs} missing"
  echo "[openclaw] this means the published tarball is broken. report at:"
  echo "  github.com/jaylfc/openclaw/issues — include the URL above and the build SHA."
  ls -la /usr/lib/node_modules/openclaw/dist/ | head -10
  exit 1
fi

echo "[openclaw] install OK"

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
: "${TAOS_FALLBACK_MODELS:=}"
: "${LITELLM_API_KEY:=}"
: "${OPENAI_API_KEY:=}"
: "${OPENAI_BASE_URL:=http://127.0.0.1:4000/v1}"
: "${TAOS_BRIDGE_URL:=http://127.0.0.1:6969}"
: "${TAOS_LOCAL_TOKEN:=}"

# Build the models[] JSON array from TAOS_MODEL + TAOS_FALLBACK_MODELS.
# Each entry: {"id":"<id>","name":"<id>","contextWindow":128000,"maxTokens":16384,"input":["text"],"reasoning":false}
_build_model_entry() {
  local id="$1"
  printf '{"id":"%s","name":"%s","contextWindow":128000,"maxTokens":16384,"input":["text"],"reasoning":false}' "$id" "$id"
}

MODELS_JSON="["
FIRST=1
if [ -n "$TAOS_MODEL" ]; then
  MODELS_JSON+="$(_build_model_entry "$TAOS_MODEL")"
  FIRST=0
fi
if [ -n "$TAOS_FALLBACK_MODELS" ]; then
  IFS=',' read -ra _FALLBACKS <<< "$TAOS_FALLBACK_MODELS"
  for _fb in "${_FALLBACKS[@]}"; do
    _fb="${_fb// /}"
    [ -z "$_fb" ] && continue
    [ "$_fb" = "$TAOS_MODEL" ] && continue
    [ "$FIRST" = "0" ] && MODELS_JSON+=","
    MODELS_JSON+="$(_build_model_entry "$_fb")"
    FIRST=0
  done
fi
MODELS_JSON+="]"

PRIMARY_REF=""
[ -n "$TAOS_MODEL" ] && PRIMARY_REF="litellm/${TAOS_MODEL}"

cat > /root/.openclaw/openclaw.json <<JSON_EOF
{
  "gateway": { "bind": "loopback", "port": 18789, "auth": { "mode": "token" }, "mode": "local" },
  "channels": {},
  "models": {
    "providers": {
      "litellm": {
        "api": "openai-completions",
        "baseUrl": "http://127.0.0.1:4000",
        "apiKey": "\${LITELLM_API_KEY}",
        "models": ${MODELS_JSON}
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "${PRIMARY_REF}"
      }
    }
  }
}
JSON_EOF
chmod 600 /root/.openclaw/openclaw.json

cat > /root/.openclaw/env <<ENV_EOF
TAOS_AGENT_NAME=${TAOS_AGENT_NAME}
TAOS_BRIDGE_URL=${TAOS_BRIDGE_URL}
TAOS_LOCAL_TOKEN=${TAOS_LOCAL_TOKEN}
TAOS_MODEL=${TAOS_MODEL}
TAOS_FALLBACK_MODELS=${TAOS_FALLBACK_MODELS}
LITELLM_API_KEY=${LITELLM_API_KEY}
OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_BASE_URL=${OPENAI_BASE_URL}
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
# Enable but do NOT start — the deployer starts the service after writing
# the llm_key to the taOS config (required for the bootstrap endpoint to
# return 200). Starting here would cause the gateway to hit HTTP 409 on
# bootstrap and crash-loop until the deployer has written the key.
systemctl enable openclaw.service

echo "[openclaw] install complete (service enabled, start deferred to deployer)"
