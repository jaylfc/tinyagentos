"""Langroid adapter — translates messages to Langroid ChatAgent calls."""
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
            from langroid import ChatAgent, ChatAgentConfig
            config = ChatAgentConfig(name=os.environ.get("TAOS_AGENT_NAME", "agent"))
            agent = ChatAgent(config)
        except ImportError:
            return {"content": "Langroid not installed in this environment"}

    try:
        result = agent.llm_response(msg.get("text", ""))
        content = result.content if hasattr(result, "content") else str(result)
        return {"content": content}
    except Exception as e:
        return {"content": f"Error: {e}"}


@app.get("/health")
async def health():
    return {"status": "ok", "framework": "langroid", "agent": os.environ.get("TAOS_AGENT_NAME", "")}


if __name__ == "__main__":
    port = int(os.environ.get("TAOS_ADAPTER_PORT", "9001"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
