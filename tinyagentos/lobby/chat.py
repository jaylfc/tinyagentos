"""Chat room engine for the lobby demo."""

from __future__ import annotations

import asyncio
import random
import time

import httpx


class ChatRoom:
    """Manages a multi-agent chat session with SSE broadcast."""

    def __init__(
        self,
        agents: list[dict],
        backend_url: str,
        topic: str,
        agents_per_round: int = 4,
        model: str = "qwen3.5:9b",
        backend_type: str | None = None,
    ):
        self.agents = agents
        self.backend_url = backend_url.rstrip("/")
        self.topic = topic
        self.agents_per_round = agents_per_round
        self.model = model
        # Auto-detect backend type from URL if not specified
        if backend_type:
            self.backend_type = backend_type
        elif "/v1" in self.backend_url:
            self.backend_type = "openai"
        else:
            self.backend_type = "ollama"
        self.messages: list[dict] = []
        self.running = False
        self._task: asyncio.Task | None = None
        self._round = 0
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def _broadcast(self, message: dict) -> None:
        self.messages.append(message)
        for q in self._subscribers:
            await q.put(message)

    async def start(self) -> None:
        self.running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        await self._broadcast({
            "name": "Moderator",
            "role": "System",
            "text": (
                f"Welcome! Today's topic: {self.topic}. "
                f"{len(self.agents)} agents are joining the discussion."
            ),
            "timestamp": time.time(),
            "avatar": None,
        })
        await asyncio.sleep(2)

        agent_queue = list(range(len(self.agents)))
        random.shuffle(agent_queue)
        idx = 0

        while self.running:
            self._round += 1
            round_agents = []
            for _ in range(self.agents_per_round):
                if idx >= len(agent_queue):
                    random.shuffle(agent_queue)
                    idx = 0
                round_agents.append(self.agents[agent_queue[idx]])
                idx += 1

            recent = self.messages[-20:]
            context = "\n".join(
                f"{m['name']} ({m['role']}): {m['text']}" for m in recent
            )

            for agent in round_agents:
                if not self.running:
                    break
                try:
                    text = await self._generate(agent, context)
                    await self._broadcast({
                        "name": agent["name"],
                        "role": agent["role"],
                        "text": text,
                        "timestamp": time.time(),
                        "avatar": agent["avatar_seed"],
                    })
                except Exception:
                    pass  # Skip failed generations silently
                await asyncio.sleep(0.5)

    async def _generate(self, agent: dict, context: str) -> str:
        if self.backend_type == "openai":
            return await self._generate_openai(agent, context)
        return await self._generate_ollama(agent, context)

    async def _generate_ollama(self, agent: dict, context: str) -> str:
        prompt = (
            f"{agent['system_prompt']}\n\nRecent conversation:\n{context}\n\n"
            f"{agent['name']}:"
        )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.backend_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.8, "num_predict": 150},
                },
            )
            resp.raise_for_status()
            return resp.json()["response"].strip()

    async def _generate_openai(self, agent: dict, context: str) -> str:
        messages = [
            {"role": "system", "content": agent["system_prompt"]},
            {
                "role": "user",
                "content": (
                    f"Recent conversation:\n{context}\n\n"
                    f"Respond as {agent['name']} in 2-3 sentences."
                ),
            },
        ]
        url = self.backend_url
        if not url.endswith("/chat/completions"):
            url = f"{url}/v1/chat/completions"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.8,
                    "max_tokens": 150,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
