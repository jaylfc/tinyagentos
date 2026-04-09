"""NanoClaw adapter — proxies messages to the NanoClaw gateway."""
import os
import uvicorn
from fastapi import FastAPI

app = FastAPI()


@app.post("/message")
async def handle_message(msg: dict):
    try:
        import httpx
        nc_url = os.environ.get("NANOCLAW_URL", "http://localhost:18789")
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{nc_url}/api/message", json={"text": msg.get("text", "")})
            if resp.status_code == 200:
                return {"content": resp.json().get("content", resp.text)}
            return {"content": f"NanoClaw returned {resp.status_code}"}
    except Exception as e:
        return {"content": f"[{os.environ.get('TAOS_AGENT_NAME', 'agent')}] NanoClaw not available: {e}"}


@app.get("/health")
async def health():
    return {"status": "ok", "framework": "nanoclaw"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("TAOS_ADAPTER_PORT", "9001")), log_level="warning")
