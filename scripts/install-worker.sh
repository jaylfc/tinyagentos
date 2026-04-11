#!/usr/bin/env bash
# TinyAgentOS worker installer — Linux + macOS
# Bootstraps a worker daemon that connects to a controller, reports live
# backend capabilities, and runs inference work dispatched by the cluster
# scheduler.
#
# Usage:
#     curl -sL https://raw.githubusercontent.com/jaylfc/tinyagentos/master/scripts/install-worker.sh | bash -s -- http://controller:6969
#
# or download + inspect + run:
#     curl -O https://raw.githubusercontent.com/jaylfc/tinyagentos/master/scripts/install-worker.sh
#     chmod +x install-worker.sh
#     ./install-worker.sh http://controller:6969
#
# Environment overrides:
#     TAOS_CONTROLLER_URL     controller URL (default: first positional arg)
#     TAOS_WORKER_NAME        worker display name (default: hostname)
#     TAOS_INSTALL_DIR        where to install (default: ~/.local/share/tinyagentos-worker)
#     TAOS_BRANCH             git branch or tag (default: master)
#     TAOS_REPO               git remote (default: https://github.com/jaylfc/tinyagentos)
#     TAOS_SKIP_BENCHMARK     if set, skip the on-join benchmark run
#     TAOS_SERVICE            install as system service: auto (default), user, skip
set -euo pipefail

CONTROLLER_URL="${TAOS_CONTROLLER_URL:-${1:-}}"
if [[ -z "$CONTROLLER_URL" ]]; then
    echo "usage: install-worker.sh <controller_url>" >&2
    echo "example: install-worker.sh http://10.0.0.5:6969" >&2
    exit 2
fi

WORKER_NAME="${TAOS_WORKER_NAME:-$(hostname -s)}"
INSTALL_DIR="${TAOS_INSTALL_DIR:-$HOME/.local/share/tinyagentos-worker}"
BRANCH="${TAOS_BRANCH:-master}"
REPO="${TAOS_REPO:-https://github.com/jaylfc/tinyagentos}"
SERVICE_MODE="${TAOS_SERVICE:-auto}"

os_name="$(uname -s)"
arch="$(uname -m)"

log() { printf '\033[1;34m[worker-install]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[worker-install]\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31m[worker-install]\033[0m %s\n' "$*" >&2; exit 1; }

log "os=$os_name arch=$arch controller=$CONTROLLER_URL name=$WORKER_NAME"
log "install_dir=$INSTALL_DIR branch=$BRANCH"

# --- system dependencies --------------------------------------------------

ensure_linux_deps() {
    if command -v apt-get >/dev/null 2>&1; then
        log "installing apt deps (python3, venv, git, curl, libtorrent)"
        sudo apt-get update -qq
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
            python3 python3-venv python3-pip git curl ca-certificates \
            libtorrent-rasterbar-dev libboost-python-dev
    elif command -v dnf >/dev/null 2>&1; then
        log "installing dnf deps (python3, git, curl, libtorrent)"
        sudo dnf install -y -q python3 python3-pip python3-virtualenv git curl \
            libtorrent-rasterbar-devel boost-python3-devel
    elif command -v pacman >/dev/null 2>&1; then
        log "installing pacman deps"
        sudo pacman -Sy --noconfirm --needed python python-pip git curl \
            libtorrent-rasterbar boost
    elif command -v apk >/dev/null 2>&1; then
        log "installing apk deps"
        sudo apk add --no-cache python3 py3-pip git curl libtorrent-rasterbar
    else
        warn "unrecognised package manager — assuming python3/git/curl/libtorrent already present"
    fi
}

ensure_macos_deps() {
    if ! command -v python3 >/dev/null 2>&1; then
        if command -v brew >/dev/null 2>&1; then
            log "installing brew python"
            brew install python git
        else
            die "python3 not found and homebrew missing. install from https://brew.sh first"
        fi
    fi
    if ! command -v git >/dev/null 2>&1; then
        die "git not found"
    fi
    # libtorrent for the model torrent mesh — brew ships it as
    # libtorrent-rasterbar with python bindings.
    if command -v brew >/dev/null 2>&1; then
        if ! brew list libtorrent-rasterbar >/dev/null 2>&1; then
            log "installing libtorrent-rasterbar via brew"
            brew install libtorrent-rasterbar || warn "brew install libtorrent-rasterbar failed — torrent path will be unavailable"
        fi
    fi
}

case "$os_name" in
    Linux) ensure_linux_deps ;;
    Darwin) ensure_macos_deps ;;
    *) die "unsupported OS: $os_name" ;;
esac

# --- accelerator detection (advisory only — never auto-installs drivers) ----
#
# We never apt/dnf/pacman a GPU driver: most boxes don't have an
# accelerator at all (Apple Silicon, Intel iGPU, ARM SBCs), and the
# ones that do typically already have the right driver from the OS
# vendor. Touching the kernel-module + DKMS stack on someone else's
# box without consent is rude.
#
# What we do instead: detect what's physically present, then surface
# clear advice if the hardware is on the bus but the driver isn't
# loaded so the worker can use it. The user runs the install command
# themselves.

detect_and_advise_accelerators() {
    [[ "$os_name" != "Linux" ]] && return 0  # macOS detection lives elsewhere

    local found_any=0

    # ── NVIDIA ───────────────────────────────────────────────────────
    local nv_devices=0 nv_driver=0 nv_userspace=0
    [[ -e /dev/nvidia0 ]] && nv_devices=1
    [[ -d /proc/driver/nvidia ]] && nv_driver=1
    command -v nvidia-smi >/dev/null 2>&1 && nv_userspace=1

    local nv_on_bus=0
    if command -v lspci >/dev/null 2>&1; then
        if lspci 2>/dev/null | grep -qi "NVIDIA Corporation"; then
            nv_on_bus=1
        fi
    fi

    if (( nv_devices || nv_driver || nv_on_bus )); then
        found_any=1
        if (( nv_driver && nv_devices )); then
            log "nvidia: kernel module loaded + device nodes present (CUDA / Vulkan available)"
            if (( ! nv_userspace )); then
                warn "nvidia-smi is not installed — VRAM size will report as unknown to the controller"
                warn "  optional: install nvidia-utils-XXX matching your driver version"
            fi
        elif (( nv_on_bus )); then
            warn "NVIDIA GPU detected on the PCIe bus but the kernel module is not loaded"
            warn "  the worker will not be able to use it until the driver is installed"
            if command -v apt-get >/dev/null 2>&1; then
                warn "  Debian / Ubuntu: sudo apt install nvidia-driver firmware-misc-nonfree && sudo reboot"
            elif command -v dnf >/dev/null 2>&1; then
                warn "  Fedora: enable RPM Fusion, then sudo dnf install akmod-nvidia xorg-x11-drv-nvidia-cuda && sudo reboot"
            elif command -v pacman >/dev/null 2>&1; then
                warn "  Arch: sudo pacman -S nvidia nvidia-utils && sudo reboot"
            else
                warn "  see your distro's NVIDIA driver documentation"
            fi
        fi
    fi

    # ── AMD ROCm / AMDGPU ───────────────────────────────────────────
    local amd_on_bus=0 amd_drm=0 amd_rocm=0
    if command -v lspci >/dev/null 2>&1; then
        if lspci 2>/dev/null | grep -qi "AMD/ATI" | head -1 >/dev/null \
           || lspci 2>/dev/null | grep -E "VGA|3D" | grep -qi "Advanced Micro Devices"; then
            amd_on_bus=1
        fi
    fi
    [[ -e /dev/kfd ]] && amd_drm=1
    [[ -d /opt/rocm ]] && amd_rocm=1

    if (( amd_on_bus || amd_drm )); then
        found_any=1
        if (( amd_rocm && amd_drm )); then
            log "amdgpu: kfd device + ROCm runtime present (HIP / Vulkan available)"
        elif (( amd_drm && ! amd_rocm )); then
            warn "AMD GPU detected with kfd device but ROCm is not installed"
            warn "  the worker will fall back to CPU until ROCm is set up"
            if command -v apt-get >/dev/null 2>&1; then
                warn "  Debian / Ubuntu: see https://rocm.docs.amd.com/projects/install-on-linux/en/latest/"
            elif command -v dnf >/dev/null 2>&1; then
                warn "  Fedora: sudo dnf install rocm-hip rocm-opencl"
            elif command -v pacman >/dev/null 2>&1; then
                warn "  Arch: sudo pacman -S rocm-hip-runtime rocm-opencl-runtime"
            fi
        elif (( amd_on_bus && ! amd_drm )); then
            warn "AMD GPU on the PCIe bus but the amdgpu kernel module is not loaded"
            warn "  ensure the amdgpu driver is enabled in your kernel and reboot"
        fi
    fi

    # ── Intel Arc / iGPU (Vulkan via Mesa) ──────────────────────────
    local intel_gpu=0
    if command -v lspci >/dev/null 2>&1; then
        if lspci 2>/dev/null | grep -E "VGA|3D" | grep -qi "Intel Corporation"; then
            intel_gpu=1
        fi
    fi
    if (( intel_gpu )); then
        found_any=1
        if [[ -d /sys/class/drm/card0 ]] || [[ -d /sys/class/drm/card1 ]]; then
            log "intel gpu: present (Vulkan via Mesa, no separate driver install needed on most distros)"
        else
            warn "Intel GPU detected on the PCIe bus but no DRM device — install mesa-vulkan-drivers"
        fi
    fi

    # ── Rockchip RKNPU ──────────────────────────────────────────────
    local rknpu_present=0
    if [[ -e /dev/rknpu ]]; then
        rknpu_present=1
    else
        for _npu_devfreq in /sys/class/devfreq/*.npu; do
            [[ -d "$_npu_devfreq" ]] && { rknpu_present=1; break; }
        done
    fi
    if (( rknpu_present )); then
        found_any=1
        # rkllama might be installed as a top-level command, or as a
        # venv-local entrypoint under ~/rkllama/rkllama-env/bin. Check
        # both — the install-rknpu.sh layout uses the venv path.
        local rkllama_found=0
        if command -v rkllama >/dev/null 2>&1; then
            rkllama_found=1
        elif [[ -x "$HOME/rkllama/rkllama-env/bin/rkllama_server" ]]; then
            rkllama_found=1
        fi
        if (( rkllama_found )); then
            log "rknpu: device present + rkllama backend installed"
        else
            warn "Rockchip NPU detected but rkllama is not installed"
            warn "  worker will run without NPU acceleration until you install rkllama"
            warn "  run: sudo bash scripts/install-rknpu.sh    (or set TAOS_RKNPU_SETUP=1 before re-running this installer to opt in automatically)"
            warn "  see: https://github.com/notpunchnox/rkllama"
            # Chained auto-install: if the caller opted in via env var,
            # run scripts/install-rknpu.sh now so rkllama is already
            # serving on :8080 before the worker systemd unit lands.
            if [[ "${TAOS_RKNPU_SETUP:-}" == "1" || "${TAOS_RKNPU_SETUP:-}" == "true" ]]; then
                local rknpu_script=""
                if [[ -x "$(dirname "$0")/install-rknpu.sh" ]]; then
                    rknpu_script="$(dirname "$0")/install-rknpu.sh"
                elif [[ -x "$INSTALL_DIR/scripts/install-rknpu.sh" ]]; then
                    rknpu_script="$INSTALL_DIR/scripts/install-rknpu.sh"
                fi
                if [[ -n "$rknpu_script" ]]; then
                    log "TAOS_RKNPU_SETUP=1 — chaining into $rknpu_script"
                    TAOS_RKNPU_SETUP=1 sudo -E bash "$rknpu_script" --yes \
                        || warn "install-rknpu.sh failed — continuing worker install anyway"
                else
                    warn "TAOS_RKNPU_SETUP=1 but install-rknpu.sh not found locally yet"
                    warn "  it will be available after the worker repo is cloned; run it then"
                fi
            fi
        fi
    fi

    # ── Apple Silicon (handled in macOS path) ───────────────────────
    if (( ! found_any )); then
        log "no discrete accelerator detected — worker will run on CPU"
    fi
}

detect_and_advise_accelerators

# --- clone / update the repo ---------------------------------------------

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
    log "cloning $REPO into $INSTALL_DIR"
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --depth 1 --branch "$BRANCH" "$REPO" "$INSTALL_DIR"
else
    log "updating existing checkout"
    (cd "$INSTALL_DIR" && git fetch --depth 1 origin "$BRANCH" && git reset --hard "origin/$BRANCH")
fi

cd "$INSTALL_DIR"

# --- python venv + worker-only deps --------------------------------------

if [[ ! -d .venv ]]; then
    log "creating venv"
    python3 -m venv .venv
fi

log "installing worker python deps into .venv"
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet \
    httpx \
    pydantic \
    psutil \
    fastapi \
    uvicorn \
    pyyaml \
    pillow \
    libtorrent

# --- first-boot benchmark -----------------------------------------------

if [[ -z "${TAOS_SKIP_BENCHMARK:-}" ]]; then
    log "running initial worker benchmark (first-join only — subsequent runs are manual)"
    ./.venv/bin/python -m tinyagentos.benchmark.runner \
        --report-to "$CONTROLLER_URL" \
        --worker-name "$WORKER_NAME" \
        --first-join \
    || warn "benchmark runner not available yet — skipping (worker will run without baseline scores)"
fi

# --- system service install ---------------------------------------------

# A system-level unit is preferred whenever the script has sudo access
# (which is always true on Linux because the apt/dnf/etc step earlier
# already used sudo). System units survive logout, run from boot, and
# avoid the PAM-session gymnastics required for `systemctl --user` on a
# fresh host where the install user has never had an active login.
#
# The user-mode path is kept as a fallback for the rare environment
# where sudo is genuinely unavailable.

have_root_or_sudo() {
    if [[ "$(id -u)" = "0" ]]; then
        return 0
    fi
    if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
        return 0
    fi
    return 1
}

install_linux_systemd_system() {
    local unit="/etc/systemd/system/tinyagentos-worker.service"
    local sudo_cmd=""
    if [[ "$(id -u)" != "0" ]]; then
        sudo_cmd="sudo"
    fi

    $sudo_cmd tee "$unit" > /dev/null <<EOF
[Unit]
Description=TinyAgentOS Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
Group=$(id -gn)
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python -m tinyagentos.worker $CONTROLLER_URL --name $WORKER_NAME
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
    log "installed $unit (system unit, runs as $USER)"
    $sudo_cmd systemctl daemon-reload
    $sudo_cmd systemctl enable --now tinyagentos-worker
    log "worker running as system service"
    log "check: systemctl status tinyagentos-worker"
    log "logs:  journalctl -u tinyagentos-worker -f"
}

install_linux_systemd_user() {
    local unit_dir="$HOME/.config/systemd/user"
    local unit="$unit_dir/tinyagentos-worker.service"
    mkdir -p "$unit_dir"
    cat > "$unit" <<EOF
[Unit]
Description=TinyAgentOS Worker
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python -m tinyagentos.worker $CONTROLLER_URL --name $WORKER_NAME
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF
    log "installed $unit (user unit fallback — sudo unavailable)"

    # Make the user manager start on boot without an active login. Must
    # happen BEFORE the systemctl --user calls so the user bus is up.
    loginctl enable-linger "$USER" 2>/dev/null || true

    # When run from a non-interactive context (curl|bash, ssh -c, etc),
    # XDG_RUNTIME_DIR may be unset and systemctl --user can't find the
    # user bus. Set it explicitly and wait briefly for the user manager
    # to come up after enable-linger.
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    local tries=0
    while [[ $tries -lt 10 ]] && ! systemctl --user is-system-running >/dev/null 2>&1; do
        sleep 1
        tries=$((tries + 1))
    done

    if ! systemctl --user daemon-reload 2>/dev/null; then
        warn "user systemd not reachable — leaving the unit on disk so it activates on next login"
        warn "to start manually: systemctl --user daemon-reload && systemctl --user enable --now tinyagentos-worker"
        return 0
    fi
    systemctl --user enable --now tinyagentos-worker
    log "worker running as user systemd service"
    log "check: systemctl --user status tinyagentos-worker"
    log "logs:  journalctl --user -u tinyagentos-worker -f"
}

install_linux_systemd() {
    if have_root_or_sudo; then
        install_linux_systemd_system
    else
        install_linux_systemd_user
    fi
}

install_macos_launchd() {
    local plist_dir="$HOME/Library/LaunchAgents"
    local plist="$plist_dir/com.tinyagentos.worker.plist"
    mkdir -p "$plist_dir"
    cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.tinyagentos.worker</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/.venv/bin/python</string>
        <string>-m</string>
        <string>tinyagentos.worker</string>
        <string>$CONTROLLER_URL</string>
        <string>--name</string>
        <string>$WORKER_NAME</string>
    </array>
    <key>WorkingDirectory</key><string>$INSTALL_DIR</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$INSTALL_DIR/worker.log</string>
    <key>StandardErrorPath</key><string>$INSTALL_DIR/worker.err</string>
</dict>
</plist>
EOF
    log "installed $plist"
    launchctl unload "$plist" 2>/dev/null || true
    launchctl load "$plist"
    log "worker running as launchd agent"
    log "check: launchctl list | grep tinyagentos"
    log "logs:  tail -f $INSTALL_DIR/worker.log"
}

if [[ "$SERVICE_MODE" == "skip" ]]; then
    log "TAOS_SERVICE=skip — not installing a service unit"
    log "run manually: cd $INSTALL_DIR && ./.venv/bin/python -m tinyagentos.worker $CONTROLLER_URL --name $WORKER_NAME"
else
    case "$os_name" in
        Linux) install_linux_systemd ;;
        Darwin) install_macos_launchd ;;
    esac
fi

log "install complete"
log "worker name: $WORKER_NAME"
log "controller:  $CONTROLLER_URL"
log "install dir: $INSTALL_DIR"
if have_root_or_sudo; then
    log "to upgrade later: cd $INSTALL_DIR && git pull && sudo systemctl restart tinyagentos-worker"
else
    log "to upgrade later: cd $INSTALL_DIR && git pull && systemctl --user restart tinyagentos-worker"
fi
