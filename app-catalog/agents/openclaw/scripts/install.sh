#!/usr/bin/env bash
# install.sh — openclaw agent runtime installer
# Runs once inside a fresh Debian bookworm LXC container.
# Pre-conditions: python3 python3-pip python3-venv python3-dev
#                 nodejs npm build-essential ca-certificates git curl
# are already installed by the deployer before this script is called.
set -euo pipefail

INSTALL_DIR=/opt/openclaw
VENV_DIR=${INSTALL_DIR}/venv
SERVICE_FILE=/etc/systemd/system/openclaw.service

echo "openclaw: starting install in ${INSTALL_DIR}"

# ---------------------------------------------------------------------------
# 1. Create install directory (idempotent)
# ---------------------------------------------------------------------------
mkdir -p "${INSTALL_DIR}"

# ---------------------------------------------------------------------------
# 2. Python venv (idempotent — skip if already exists)
# ---------------------------------------------------------------------------
if [ ! -d "${VENV_DIR}" ]; then
    echo "openclaw: creating Python venv at ${VENV_DIR}"
    python3 -m venv "${VENV_DIR}"
fi

# ---------------------------------------------------------------------------
# 3. Install Python dependencies (pinned for reproducible arm64 builds)
# ---------------------------------------------------------------------------
echo "openclaw: installing Python packages"
"${VENV_DIR}/bin/pip" install --no-cache-dir \
    "fastapi==0.115.0" \
    "uvicorn[standard]==0.32.0" \
    "httpx==0.27.2" \
    "openai==1.54.0"

# ---------------------------------------------------------------------------
# 4. Write runtime server
# ---------------------------------------------------------------------------
echo "openclaw: writing server.py"
cat > "${INSTALL_DIR}/server.py" << 'PYEOF'
"""Minimal openclaw agent runtime — bridges the host chat router to the
host LiteLLM proxy. Runs inside the agent's LXC container on port 8100.

Reads env injected by the deployer:
  TAOS_AGENT_NAME   — display label returned in every response
  TAOS_MODEL        — model id to pass to LiteLLM (falls back to "default")
  OPENAI_BASE_URL   — LiteLLM /v1 root on the host
  OPENAI_API_KEY    — per-agent virtual key minted by LiteLLM

No persistence, no tools, no retries beyond the OpenAI SDK's own defaults.
The host owns memory and skills; the container is disposable.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("openclaw")

AGENT_NAME = os.environ.get("TAOS_AGENT_NAME", "openclaw")
MODEL = os.environ.get("TAOS_MODEL") or "default"
BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://host.docker.internal:4000/v1")
API_KEY = os.environ.get("OPENAI_API_KEY", "")

client = OpenAI(base_url=BASE_URL, api_key=API_KEY or "sk-no-key")

app = FastAPI(title=f"openclaw-{AGENT_NAME}")


class MessageIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: str
    from_name: Optional[str] = Field(default=None, alias="from")
    thread_id: Optional[str] = None


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "agent": AGENT_NAME,
        "model": MODEL,
        "base_url": BASE_URL,
        "has_key": bool(API_KEY),
    }


@app.post("/message")
def handle_message(msg: MessageIn) -> dict[str, Any]:
    sender = msg.from_name or "user"
    logger.info("message from %s: %s", sender, msg.text[:120])
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": f"You are {AGENT_NAME}, a helpful assistant."},
                {"role": "user", "content": msg.text},
            ],
            timeout=120,
        )
        content = (resp.choices[0].message.content or "").strip()
        return {"content": content, "thread_id": msg.thread_id}
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM call failed")
        return {"content": f"[openclaw error] {exc}", "thread_id": msg.thread_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100, log_level="info")
PYEOF

# ---------------------------------------------------------------------------
# 5. Write systemd unit
# ---------------------------------------------------------------------------
echo "openclaw: writing systemd unit"
cat > "${SERVICE_FILE}" << 'SVCEOF'
[Unit]
Description=openclaw agent runtime
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=-/etc/openclaw.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/openclaw/venv/bin/python /opt/openclaw/server.py
Restart=on-failure
RestartSec=3
User=root
WorkingDirectory=/opt/openclaw
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SVCEOF

# ---------------------------------------------------------------------------
# 6. Enable and start the service (systemd primary path; nohup fallback)
# ---------------------------------------------------------------------------
if command -v systemctl > /dev/null 2>&1; then
    echo "openclaw: enabling and starting openclaw.service via systemd"
    systemctl daemon-reload
    systemctl enable --now openclaw.service
else
    echo "openclaw: systemctl not found, falling back to nohup"
    nohup "${VENV_DIR}/bin/python" "${INSTALL_DIR}/server.py" \
        > /var/log/openclaw.log 2>&1 &
fi

# ---------------------------------------------------------------------------
# 7. Wait up to 20s for the health endpoint to respond
# ---------------------------------------------------------------------------
echo "openclaw: waiting for health endpoint on port 8100"
RETRIES=10
for i in $(seq 1 ${RETRIES}); do
    if curl -sf http://127.0.0.1:8100/health > /dev/null 2>&1; then
        echo "openclaw: ready on port 8100"
        exit 0
    fi
    echo "openclaw: not ready yet (attempt ${i}/${RETRIES}), retrying in 2s..."
    sleep 2
done

echo "openclaw: ERROR — health check failed after $((RETRIES * 2))s" >&2
exit 1
