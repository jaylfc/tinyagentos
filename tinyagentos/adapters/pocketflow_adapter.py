"""PocketFlow adapter — translates messages to PocketFlow graph execution calls."""
import os
import uvicorn
from fastapi import FastAPI

app = FastAPI()
flow = None


@app.post("/message")
async def handle_message(msg: dict):
    global flow
    if flow is None:
        try:
            from pocketflow import Flow
            flow = Flow()
        except ImportError:
            return {"content": "PocketFlow not installed in this environment"}

    try:
        result = flow.run(msg.get("text", ""))
        return {"content": str(result)}
    except Exception as e:
        return {"content": f"Error: {e}"}


@app.get("/health")
async def health():
    return {"status": "ok", "framework": "pocketflow", "agent": os.environ.get("TAOS_AGENT_NAME", "")}


if __name__ == "__main__":
    port = int(os.environ.get("TAOS_ADAPTER_PORT", "9001"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
