"""PicoClaw adapter — NPU-aware micro agent."""
import os
import uvicorn
from fastapi import FastAPI

app = FastAPI()


@app.post("/message")
async def handle_message(msg: dict):
    try:
        import picoclaw
        agent = picoclaw.Agent()
        result = agent.run(msg.get("text", ""))
        return {"content": str(result)}
    except ImportError:
        return {"content": f"[{os.environ.get('TAOS_AGENT_NAME', 'agent')}] PicoClaw not installed"}


@app.get("/health")
async def health():
    return {"status": "ok", "framework": "picoclaw"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("TAOS_ADAPTER_PORT", "9001")), log_level="warning")
