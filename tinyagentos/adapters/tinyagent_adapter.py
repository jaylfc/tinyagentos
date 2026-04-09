"""TinyAgent adapter — proxies messages to TinyAgent's server mode."""
import os
import uvicorn
from fastapi import FastAPI

app = FastAPI()


@app.post("/message")
async def handle_message(msg: dict):
    try:
        import httpx
        ta_url = os.environ.get("TINYAGENT_URL", "http://localhost:5000")
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{ta_url}/run", json={"query": msg.get("text", "")})
            if resp.status_code == 200:
                return {"content": resp.json().get("response", resp.text)}
            return {"content": f"TinyAgent returned {resp.status_code}"}
    except Exception as e:
        return {"content": f"[{os.environ.get('TAOS_AGENT_NAME', 'agent')}] TinyAgent not available: {e}"}


@app.get("/health")
async def health():
    return {"status": "ok", "framework": "tinyagent"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("TAOS_ADAPTER_PORT", "9001")), log_level="warning")
