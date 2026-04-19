#!/bin/bash
set -euo pipefail
log() { echo "[$(date -u +%H:%M:%S)] langroid-install: $*"; }
AGENT_NAME="${TAOS_AGENT_NAME:?}"; LLM_KEY="${LITELLM_API_KEY:?}"
BRIDGE_URL="${TAOS_BRIDGE_URL:?}"; LOCAL_TOKEN="${TAOS_LOCAL_TOKEN:?}"
MODEL="${TAOS_MODEL:-kilo-auto/free}"
log "pip install langroid + deps"
pip3 install --break-system-packages --quiet langroid httpx 2>&1 | tail -3
mkdir -p /opt/taos
cat > /opt/taos/taos-langroid-bridge.py <<'BRIDGE_EOF'
#!/usr/bin/env python3
"""taOS-Langroid bridge."""
from __future__ import annotations
import asyncio, json, logging, os, signal
from concurrent.futures import ThreadPoolExecutor
import httpx
logging.basicConfig(level=logging.INFO, format="%(asctime)s [langroid-bridge] %(message)s")
log = logging.getLogger("langroid-bridge")
BRIDGE_URL = os.environ["TAOS_BRIDGE_URL"]; AGENT_NAME = os.environ["TAOS_AGENT_NAME"]
LOCAL_TOKEN = os.environ["TAOS_LOCAL_TOKEN"]; MODEL = os.environ.get("TAOS_MODEL", "kilo-auto/free")
_pool = ThreadPoolExecutor(max_workers=2); _agent = None
def _build():
    global _agent
    if _agent: return _agent
    import langroid as lr
    _agent = lr.ChatAgent(lr.ChatAgentConfig(
        llm=lr.language_models.OpenAIGPTConfig(chat_model=MODEL),
    ))
    return _agent
def _run(text: str) -> str:
    try:
        a = _build(); r = a.llm_response(text)
        return r.content if r else "(no response)"
    except Exception as e: return f"[langroid error: {e}]"
async def fetch_boot(c): r = await c.get(f"{BRIDGE_URL}/api/openclaw/bootstrap?agent={AGENT_NAME}", headers={"Authorization": f"Bearer {LOCAL_TOKEN}"}, timeout=30); r.raise_for_status(); return r.json()
async def post_reply(c, u, t, mid, tid, txt, cid=None):
    try: await c.post(u, json={"kind":"final","id":mid,"trace_id":tid,"content":txt}, headers={"Authorization":f"Bearer {t}"}, timeout=30)
    except Exception as e: log.warning("reply: %s", e)
async def handle(c, evt, ch):
    mid=evt.get("id",""); tid=evt.get("trace_id",mid); txt=evt.get("text","")
    log.info("user_message id=%s text=%r", mid, txt[:80])
    loop = asyncio.get_running_loop()
    reply = await loop.run_in_executor(_pool, _run, txt)
    await post_reply(c, ch["reply_url"], ch["auth_bearer"], mid, tid, reply)
async def sse(c, ch, stop):
    while not stop.is_set():
        try:
            async with c.stream("GET", ch["events_url"], headers={"Authorization":f"Bearer {ch['auth_bearer']}","Accept":"text/event-stream"}, timeout=None) as r:
                if r.status_code != 200: await asyncio.sleep(2); continue
                t,d = "",""
                async for raw in r.aiter_lines():
                    if stop.is_set(): break
                    if raw == "":
                        if t=="user_message" and d:
                            try: asyncio.create_task(handle(c, json.loads(d), ch))
                            except Exception as e: log.warning("parse: %s", e)
                        t,d = "",""; continue
                    if raw.startswith(":"): continue
                    if raw.startswith("event:"): t = raw[6:].strip()
                    elif raw.startswith("data:"): d = raw[5:].lstrip()
        except Exception as e: log.warning("sse: %s", e)
        if not stop.is_set(): await asyncio.sleep(2)
async def main():
    stop = asyncio.Event(); loop = asyncio.get_running_loop()
    for s in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(s, stop.set)
    async with httpx.AsyncClient() as c:
        boot = await fetch_boot(c); log.info("bootstrap OK agent=%s", boot.get("agent_name"))
        await sse(c, boot["channel"], stop)
asyncio.run(main())
BRIDGE_EOF
chmod +x /opt/taos/taos-langroid-bridge.py
cat > /etc/systemd/system/taos-langroid-bridge.service <<UNIT
[Unit]
Description=taOS-langroid bridge
After=network.target
[Service]
Type=simple
Environment=TAOS_BRIDGE_URL=$BRIDGE_URL
Environment=TAOS_AGENT_NAME=$AGENT_NAME
Environment=TAOS_LOCAL_TOKEN=$LOCAL_TOKEN
Environment=LITELLM_API_KEY=$LLM_KEY
Environment=TAOS_MODEL=$MODEL
Environment=OPENAI_API_KEY=$LLM_KEY
Environment=OPENAI_API_BASE=http://127.0.0.1:4000/v1
Environment=OPENAI_BASE_URL=http://127.0.0.1:4000/v1
ExecStart=/usr/bin/python3 /opt/taos/taos-langroid-bridge.py
Restart=on-failure
RestartSec=5
StandardOutput=append:/var/log/taos-langroid-bridge.log
StandardError=append:/var/log/taos-langroid-bridge.log
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now taos-langroid-bridge.service
echo "langroid-1.x" > /opt/taos/framework.version
log done

