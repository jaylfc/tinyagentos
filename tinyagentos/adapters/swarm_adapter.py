"""Swarm adapter — translates messages to OpenAI Swarm agent calls."""
import os
import uvicorn
from fastapi import FastAPI

app = FastAPI()


@app.post("/message")
async def handle_message(msg: dict):
    try:
        from swarm import Swarm, Agent
        from openai import OpenAI
        client = Swarm(client=OpenAI())
        agent = Agent(name="assistant", instructions="You are a helpful assistant.")
        response = client.run(agent=agent, messages=[{"role": "user", "content": msg.get("text", "")}])
        return {"content": response.messages[-1]["content"]}
    except ImportError:
        return {"content": f"[{os.environ.get('TAOS_AGENT_NAME', 'agent')}] Swarm not installed"}


@app.get("/health")
async def health():
    return {"status": "ok", "framework": "swarm", "agent": os.environ.get("TAOS_AGENT_NAME", "")}


if __name__ == "__main__":
    port = int(os.environ.get("TAOS_ADAPTER_PORT", "9001"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
