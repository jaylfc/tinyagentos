"""SmolAgents adapter — translates messages to SmolAgents code agent calls."""
import os
import uvicorn
from fastapi import FastAPI

app = FastAPI()
agent = None


@app.post("/message")
async def handle_message(msg: dict):
    global agent
    if agent is None:
        try:
            from smolagents import CodeAgent, LiteLLMModel
            model = LiteLLMModel(model_id="default")
            agent = CodeAgent(model=model, tools=[])
        except ImportError:
            return {"content": "SmolAgents not installed in this environment"}

    try:
        result = agent.run(msg.get("text", ""))
        return {"content": str(result)}
    except Exception as e:
        return {"content": f"Error: {e}"}


@app.get("/health")
async def health():
    return {"status": "ok", "framework": "smolagents", "agent": os.environ.get("TAOS_AGENT_NAME", "")}


if __name__ == "__main__":
    port = int(os.environ.get("TAOS_ADAPTER_PORT", "9001"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
