#!/usr/bin/env bash
# taos-deploy-helper.sh — privileged backend deployment on a TAOS worker.
#
# Called by the worker agent when the controller requests a backend install.
# This script runs with NOPASSWD sudo via a sudoers drop-in installed by
# install-worker.sh, so the worker service never needs to prompt for a
# password or run as root itself.
#
# Usage:
#   taos-deploy-helper.sh install-ollama
#   taos-deploy-helper.sh install-exo
#   taos-deploy-helper.sh install-llama-cpp [--cuda]
#   taos-deploy-helper.sh install-vllm
#   taos-deploy-helper.sh install-rknpu
#   taos-deploy-helper.sh update-worker
#   taos-deploy-helper.sh status
#
# Security: this script is allowlisted in sudoers with a fixed path and
# only the commands below are reachable. The worker cannot execute
# arbitrary commands as root.
set -euo pipefail

INSTALL_DIR="${TAOS_INSTALL_DIR:-$HOME/.local/share/tinyagentos-worker}"
REPO="${TAOS_REPO:-https://github.com/jaylfc/tinyagentos}"
BRANCH="${TAOS_BRANCH:-master}"

log() { printf '[taos-deploy] %s\n' "$*"; }
die() { printf '[taos-deploy] ERROR: %s\n' "$*" >&2; exit 1; }

cmd_install_ollama() {
    log "installing TAOS-namespaced Ollama on port 21434"
    if command -v apt-get >/dev/null 2>&1; then
        curl -fsSL https://ollama.com/install.sh | OLLAMA_HOST=127.0.0.1:21434 sh
    elif command -v dnf >/dev/null 2>&1; then
        curl -fsSL https://ollama.com/install.sh | OLLAMA_HOST=127.0.0.1:21434 sh
    else
        die "unsupported package manager for Ollama install"
    fi
    log "ollama installed"
}

cmd_install_exo() {
    log "installing exo distributed inference"
    local exo_dir="$INSTALL_DIR/exo"
    if [[ -d "$exo_dir" ]]; then
        cd "$exo_dir" && git pull --ff-only
    else
        git clone https://github.com/exo-explore/exo.git "$exo_dir"
        cd "$exo_dir"
    fi

    if ! command -v uv >/dev/null 2>&1; then
        log "installing uv package manager"
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    fi

    uv sync --all-packages
    if command -v just >/dev/null 2>&1; then
        just build-dashboard
    else
        log "just not found, skipping dashboard build"
    fi

    # Create a systemd unit for exo
    local unit="/etc/systemd/system/taos-exo.service"
    cat > "$unit" <<UNIT
[Unit]
Description=TAOS Exo Distributed Inference
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$exo_dir
ExecStart=$HOME/.local/bin/uv run exo
Restart=on-failure
RestartSec=5
Environment=HOME=$HOME
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable --now taos-exo.service
    log "exo installed and running as taos-exo.service"
}

cmd_install_llama_cpp() {
    local cuda_flag=""
    if [[ "${1:-}" == "--cuda" ]]; then
        cuda_flag="-DGGML_CUDA=ON"
    fi

    log "installing llama.cpp (TurboQuant fork)${cuda_flag:+ with CUDA}"
    local llama_dir="$INSTALL_DIR/llama-cpp-turboquant"
    if [[ -d "$llama_dir" ]]; then
        cd "$llama_dir" && git pull --ff-only
    else
        git clone https://github.com/TheTom/llama-cpp-turboquant.git "$llama_dir"
        cd "$llama_dir"
        git checkout tqp-v0.1.0
    fi

    if ! command -v cmake >/dev/null 2>&1; then
        if command -v apt-get >/dev/null 2>&1; then
            apt-get install -y -qq cmake build-essential
        elif command -v dnf >/dev/null 2>&1; then
            dnf install -y -q cmake gcc-c++ make
        fi
    fi

    cmake -B build -DCMAKE_BUILD_TYPE=Release $cuda_flag
    cmake --build build --config Release -j"$(nproc)"
    log "llama.cpp built at $llama_dir/build/bin/"
}

cmd_install_vllm() {
    log "installing vLLM"
    local venv="$INSTALL_DIR/.venv"
    if [[ -d "$venv" ]]; then
        "$venv/bin/pip" install vllm
    else
        die "worker venv not found at $venv"
    fi
    log "vLLM installed into worker venv"
}

cmd_install_rknpu() {
    log "running RKNPU install script"
    if [[ -f "$INSTALL_DIR/tinyagentos/scripts/install-rknpu.sh" ]]; then
        bash "$INSTALL_DIR/tinyagentos/scripts/install-rknpu.sh"
    else
        curl -fsSL https://raw.githubusercontent.com/jaylfc/tinyagentos/$BRANCH/scripts/install-rknpu.sh | bash
    fi
    log "RKNPU stack installed"
}

cmd_update_worker() {
    log "updating worker from $BRANCH"
    local repo_dir="$INSTALL_DIR/tinyagentos"
    if [[ -d "$repo_dir" ]]; then
        cd "$repo_dir" && git pull --ff-only origin "$BRANCH"
        "$INSTALL_DIR/.venv/bin/pip" install -q -e ".[worker]"
    else
        die "worker repo not found at $repo_dir"
    fi
    systemctl restart tinyagentos-worker.service 2>/dev/null || true
    log "worker updated and restarted"
}

cmd_status() {
    echo '{'
    echo '  "deploy_helper": "ok",'
    echo "  \"install_dir\": \"$INSTALL_DIR\","

    local backends=()
    systemctl is-active taos-ollama.service >/dev/null 2>&1 && backends+=("ollama")
    systemctl is-active taos-exo.service >/dev/null 2>&1 && backends+=("exo")
    [[ -x "$INSTALL_DIR/llama-cpp-turboquant/build/bin/llama-server" ]] && backends+=("llama-cpp")

    printf '  "installed_backends": [%s]\n' "$(printf '"%s",' "${backends[@]}" | sed 's/,$//')"
    echo '}'
}

# --- dispatch ---------------------------------------------------------------
case "${1:-help}" in
    install-ollama)   cmd_install_ollama ;;
    install-exo)      cmd_install_exo ;;
    install-llama-cpp) shift; cmd_install_llama_cpp "$@" ;;
    install-vllm)     cmd_install_vllm ;;
    install-rknpu)    cmd_install_rknpu ;;
    update-worker)    cmd_update_worker ;;
    status)           cmd_status ;;
    help|*)
        echo "usage: taos-deploy-helper.sh <command>"
        echo "commands: install-ollama, install-exo, install-llama-cpp [--cuda],"
        echo "          install-vllm, install-rknpu, update-worker, status"
        exit 1
        ;;
esac
