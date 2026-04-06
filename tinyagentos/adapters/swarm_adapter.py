"""Swarm adapter — translates messages to OpenAI Swarm agent calls."""
import os
import uvicorn
from fastapi import FastAPI

app = FastAPI()
swarm_client = None
swarm_agent = None


@app.post("/message")
async def handle_message(msg: dict):
    global swarm_client, swarm_agent
    if swarm_client is None:
        try:
            from swarm import Swarm, Agent
            swarm_client = Swarm()
            swarm_agent = Agent(name=os.environ.get("TAOS_AGENT_NAME", "agent"))
        except ImportError:
            return {"content": "Swarm not installed in this environment"}

    try:
        response = swarm_client.run(
            agent=swarm_agent,
            messages=[{"role": "user", "content": msg.get("text", "")}],
        )
        content = response.messages[-1]["content"] if response.messages else ""
        return {"content": content}
    except Exception as e:
        return {"content": f"Error: {e}"}


@app.get("/health")
async def health():
    return {"status": "ok", "framework": "swarm", "agent": os.environ.get("TAOS_AGENT_NAME", "")}


if __name__ == "__main__":
    port = int(os.environ.get("TAOS_ADAPTER_PORT", "9001"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
