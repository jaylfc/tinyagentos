#!/usr/bin/env bash
# TinyAgentOS worker uninstaller — Linux + macOS
set -euo pipefail

INSTALL_DIR="${TAOS_INSTALL_DIR:-$HOME/.local/share/tinyagentos-worker}"
os_name="$(uname -s)"

log() { printf '\033[1;34m[worker-uninstall]\033[0m %s\n' "$*"; }

case "$os_name" in
    Linux)
        systemctl --user stop tinyagentos-worker 2>/dev/null || true
        systemctl --user disable tinyagentos-worker 2>/dev/null || true
        rm -f "$HOME/.config/systemd/user/tinyagentos-worker.service"
        systemctl --user daemon-reload 2>/dev/null || true
        log "removed user systemd service"
        ;;
    Darwin)
        launchctl unload "$HOME/Library/LaunchAgents/com.tinyagentos.worker.plist" 2>/dev/null || true
        rm -f "$HOME/Library/LaunchAgents/com.tinyagentos.worker.plist"
        log "removed launchd agent"
        ;;
esac

if [[ -d "$INSTALL_DIR" ]]; then
    log "removing $INSTALL_DIR"
    rm -rf "$INSTALL_DIR"
fi

log "uninstall complete"
