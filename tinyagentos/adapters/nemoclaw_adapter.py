"""NemoClaw adapter — proxies messages to the NemoClaw gateway (OpenClaw inside k3s)."""
import os
import uvicorn
from fastapi import FastAPI

app = FastAPI()


@app.post("/message")
async def handle_message(msg: dict):
    try:
        import httpx
        nemo_url = os.environ.get("NEMOCLAW_URL", "http://localhost:18789")
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{nemo_url}/api/message", json={"text": msg.get("text", "")})
            if resp.status_code == 200:
                return {"content": resp.json().get("content", resp.text)}
            return {"content": f"NemoClaw returned {resp.status_code}"}
    except Exception as e:
        return {"content": f"[{os.environ.get('TAOS_AGENT_NAME', 'agent')}] NemoClaw not available: {e}"}


@app.get("/health")
async def health():
    return {"status": "ok", "framework": "nemoclaw"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("TAOS_ADAPTER_PORT", "9001")), log_level="warning")
