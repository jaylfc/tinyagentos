#!/bin/bash
# Install Hermes inside an LXC agent container + the taOS-Hermes bridge.
# Hermes manages its own systemd service when invoked with --run-as-user
# (required inside LXC), so we don't write our own unit for it.
set -euo pipefail
log() { echo "[$(date -u +%H:%M:%S)] hermes-install: $*"; }
AGENT_NAME="${TAOS_AGENT_NAME:?TAOS_AGENT_NAME required}"
LLM_KEY="${LITELLM_API_KEY:?LITELLM_API_KEY required}"
BRIDGE_URL="${TAOS_BRIDGE_URL:?TAOS_BRIDGE_URL required}"
LOCAL_TOKEN="${TAOS_LOCAL_TOKEN:?TAOS_LOCAL_TOKEN required}"
MODEL="${TAOS_MODEL:-kilo-auto/free}"
log "installing uv"
if ! command -v uv >/dev/null 2>&1 && [ ! -x /root/.local/bin/uv ]; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="/root/.local/bin:$PATH"
echo 'export PATH="/root/.local/bin:$PATH"' >> /root/.bashrc
if [ ! -d /root/.hermes/hermes-agent ]; then
    log "running Hermes installer (--skip-setup)"
    curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash -s -- --skip-setup
fi
HERMES_BIN=""
for c in /root/.local/bin/hermes /root/.hermes/hermes-agent/.venv/bin/hermes; do
    [ -x "$c" ] && HERMES_BIN="$c" && break
done
[ -z "$HERMES_BIN" ] && HERMES_BIN=$(command -v hermes || true)
[ -z "$HERMES_BIN" ] && { log "ERROR: hermes binary not found"; exit 2; }
log "hermes at $HERMES_BIN"
log "writing Hermes config"
mkdir -p /root/.hermes /root/.hermes/gateway
cat > /root/.hermes/cli-config.yaml <<EOF
model:
  default: "$MODEL"
  provider: custom
  base_url: http://127.0.0.1:4000/v1
EOF
cat > /root/.hermes/.env <<EOF
OPENAI_API_KEY=$LLM_KEY
OPENAI_BASE_URL=http://127.0.0.1:4000/v1
HERMES_INFERENCE_PROVIDER=custom
HERMES_DEFAULT_MODEL=$MODEL
EOF
chmod 600 /root/.hermes/.env
cat > /root/.hermes/gateway/config.yaml <<EOF
platforms:
  api_server:
    enabled: true
    host: 127.0.0.1
    port: 8642
EOF
log "starting Hermes gateway (Hermes installs its own systemd unit)"
"$HERMES_BIN" gateway start --run-as-user root 2>&1 | tail -10 || log "WARN: hermes gateway start exited non-zero"
log "pip install httpx for taOS bridge"
pip3 install --break-system-packages --quiet httpx 2>&1 | tail -3 || true
log "writing taOS-Hermes bridge"
mkdir -p /opt/taos
cat > /opt/taos/taos-hermes-bridge.py <<'BRIDGE_EOF'
#!/usr/bin/env python3
"""taOS-Hermes bridge: subscribes to taOS SSE for this agent, forwards
user messages to the local Hermes api_server (/v1/chat/completions) at
127.0.0.1:8642, and POSTs replies back to taOS via the openclaw reply
URL. Lets Hermes participate in chat through the existing
agent_chat_router → bridge_session pipeline that openclaw uses today —
no taOS-side changes required.

Env (injected by deployer): TAOS_BRIDGE_URL, TAOS_AGENT_NAME,
TAOS_LOCAL_TOKEN, LITELLM_API_KEY (optional, for hermes auth).

Stdlib + httpx only. No openclaw coupling.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [hermes-bridge] %(message)s")
log = logging.getLogger("hermes-bridge")

BRIDGE_URL = os.environ["TAOS_BRIDGE_URL"]
AGENT_NAME = os.environ["TAOS_AGENT_NAME"]
LOCAL_TOKEN = os.environ["TAOS_LOCAL_TOKEN"]
HERMES_URL = os.environ.get("HERMES_API_URL", "http://127.0.0.1:8642")
HERMES_KEY = os.environ.get("LITELLM_API_KEY", "")
HERMES_MODEL = os.environ.get("TAOS_MODEL", "kilo-auto/free")
RECONNECT_DELAY = 2.0


async def fetch_bootstrap(client: httpx.AsyncClient) -> dict:
    url = f"{BRIDGE_URL}/api/openclaw/bootstrap?agent={AGENT_NAME}"
    resp = await client.get(url, headers={"Authorization": f"Bearer {LOCAL_TOKEN}"}, timeout=30)
    resp.raise_for_status()
    boot = resp.json()
    if boot.get("schema_version") != 1:
        raise RuntimeError(f"unsupported bootstrap schema_version={boot.get('schema_version')}")
    return boot


async def call_hermes(client: httpx.AsyncClient, text: str) -> str:
    """Call Hermes' OpenAI-compatible /v1/chat/completions and return the
    assistant's reply text. Errors return a short error string so the
    user always sees something."""
    payload = {
        "model": HERMES_MODEL,
        "messages": [{"role": "user", "content": text}],
    }
    headers = {"Content-Type": "application/json"}
    if HERMES_KEY:
        headers["Authorization"] = f"Bearer {HERMES_KEY}"
    try:
        resp = await client.post(f"{HERMES_URL}/v1/chat/completions",
                                  json=payload, headers=headers, timeout=120)
        if resp.status_code != 200:
            return f"[hermes returned {resp.status_code}: {resp.text[:200]}]"
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[hermes error: {e}]"


async def post_reply(client: httpx.AsyncClient, reply_url: str, token: str,
                     msg_id: str, trace_id: str, content: str) -> None:
    body = {"kind": "final", "id": msg_id, "trace_id": trace_id, "content": content}
    try:
        resp = await client.post(reply_url, json=body,
                                  headers={"Content-Type": "application/json",
                                           "Authorization": f"Bearer {token}"},
                                  timeout=30)
        if resp.status_code >= 400:
            log.warning("reply POST %s: %s", resp.status_code, resp.text[:300])
    except Exception as e:
        log.warning("reply POST failed: %s", e)


async def handle_user_message(client: httpx.AsyncClient, evt: dict, channel: dict) -> None:
    msg_id = evt.get("id", "")
    trace_id = evt.get("trace_id", msg_id)
    text = evt.get("text", "")
    log.info("user_message id=%s text=%r", msg_id, text[:80])
    reply = await call_hermes(client, text)
    await post_reply(client, channel["reply_url"], channel["auth_bearer"],
                     msg_id, trace_id, reply)


async def sse_loop(client: httpx.AsyncClient, channel: dict, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            log.info("SSE connecting to %s", channel["events_url"])
            async with client.stream("GET", channel["events_url"],
                                      headers={"Authorization": f"Bearer {channel['auth_bearer']}",
                                               "Accept": "text/event-stream",
                                               "Cache-Control": "no-cache"},
                                      timeout=None) as resp:
                if resp.status_code != 200:
                    log.warning("SSE %s — retry", resp.status_code)
                    await asyncio.sleep(RECONNECT_DELAY)
                    continue
                log.info("SSE connected")
                evt_type = ""
                evt_data = ""
                async for raw in resp.aiter_lines():
                    if stop.is_set():
                        break
                    if raw == "":
                        if evt_type == "user_message" and evt_data:
                            try:
                                evt = json.loads(evt_data)
                                asyncio.create_task(handle_user_message(client, evt, channel))
                            except Exception as e:
                                log.warning("parse error: %s", e)
                        evt_type, evt_data = "", ""
                        continue
                    if raw.startswith(":"):
                        continue
                    if raw.startswith("event:"):
                        evt_type = raw[6:].strip()
                    elif raw.startswith("data:"):
                        evt_data = raw[5:].lstrip()
        except Exception as e:
            log.warning("SSE error: %s; retry in %ds", e, RECONNECT_DELAY)
        if not stop.is_set():
            await asyncio.sleep(RECONNECT_DELAY)


async def main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    async with httpx.AsyncClient() as client:
        # Wait for Hermes api_server to be healthy
        for i in range(40):
            try:
                r = await client.get(f"{HERMES_URL}/health", timeout=5)
                if r.status_code == 200:
                    log.info("Hermes api_server healthy")
                    break
            except Exception:
                pass
            await asyncio.sleep(3)
        else:
            log.warning("Hermes api_server health never returned 200; continuing anyway")

        boot = await fetch_bootstrap(client)
        channel = boot["channel"]
        log.info("bootstrap OK: agent=%s session=%s", boot.get("agent_name"), boot.get("session_id"))
        await sse_loop(client, channel, stop)


if __name__ == "__main__":
    asyncio.run(main())
BRIDGE_EOF
chmod +x /opt/taos/taos-hermes-bridge.py
cat > /etc/systemd/system/taos-hermes-bridge.service <<EOF
[Unit]
Description=taOS-Hermes bridge
After=network.target
[Service]
Type=simple
Environment=TAOS_BRIDGE_URL=$BRIDGE_URL
Environment=TAOS_AGENT_NAME=$AGENT_NAME
Environment=TAOS_LOCAL_TOKEN=$LOCAL_TOKEN
Environment=LITELLM_API_KEY=$LLM_KEY
Environment=TAOS_MODEL=$MODEL
Environment=HERMES_API_URL=http://127.0.0.1:8642
ExecStart=/usr/bin/python3 /opt/taos/taos-hermes-bridge.py
Restart=on-failure
RestartSec=5
StandardOutput=append:/var/log/taos-hermes-bridge.log
StandardError=append:/var/log/taos-hermes-bridge.log
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
log "waiting for Hermes :8642 (up to 90s)"
HERMES_READY=0
for i in $(seq 1 30); do
    sleep 3
    if curl -fsS http://127.0.0.1:8642/health > /dev/null 2>&1; then
        log "Hermes api_server ready (after $((i*3))s)"
        HERMES_READY=1; break
    fi
done
systemctl enable --now taos-hermes-bridge.service
mkdir -p /opt/taos
echo "hermes-0.1" > /opt/taos/framework.version
[ "$HERMES_READY" -eq 0 ] && log "WARN: Hermes :8642 not up in 90s; bridge will retry"
log "done"

