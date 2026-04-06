from __future__ import annotations
import logging
import httpx
from tinyagentos.channel_hub.message import IncomingMessage, OutgoingMessage, parse_inline_hints

logger = logging.getLogger(__name__)


class MessageRouter:
    def __init__(self):
        self._agent_ports: dict[str, int] = {}  # agent_name -> adapter port
        self._channel_assignments: dict[str, str] = {}  # "platform:bot_id" -> agent_name
        self._next_port = 9001

    def assign_channel(self, platform: str, bot_id: str, agent_name: str):
        key = f"{platform}:{bot_id}"
        self._channel_assignments[key] = agent_name

    def get_agent_for_channel(self, platform: str, bot_id: str) -> str | None:
        return self._channel_assignments.get(f"{platform}:{bot_id}")

    def register_adapter(self, agent_name: str, port: int):
        self._agent_ports[agent_name] = port

    def get_adapter_port(self, agent_name: str) -> int | None:
        return self._agent_ports.get(agent_name)

    def allocate_port(self, agent_name: str) -> int:
        port = self._next_port
        self._next_port += 1
        self._agent_ports[agent_name] = port
        return port

    async def route_message(self, agent_name: str, message: IncomingMessage) -> OutgoingMessage | None:
        port = self._agent_ports.get(agent_name)
        if not port:
            logger.warning(f"No adapter registered for agent '{agent_name}'")
            return None
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"http://localhost:{port}/message",
                    json={
                        "id": message.id,
                        "from_id": message.from_id,
                        "from_name": message.from_name,
                        "platform": message.platform,
                        "channel_id": message.channel_id,
                        "text": message.text,
                        "attachments": message.attachments,
                        "reply_to": message.reply_to,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                # Check if response is structured or plain text with hints
                if isinstance(data.get("content"), str) and not data.get("buttons"):
                    # Try parsing inline hints from plain text
                    parsed = parse_inline_hints(data["content"])
                    if parsed.buttons or parsed.images:
                        return parsed

                return OutgoingMessage(
                    content=data.get("content", ""),
                    buttons=data.get("buttons", []),
                    images=data.get("images", []),
                    cards=data.get("cards", []),
                    reply_to=data.get("reply_to"),
                    passthrough=data.get("passthrough", False),
                    passthrough_platform=data.get("platform", ""),
                    passthrough_payload=data.get("payload", {}),
                )
        except Exception as e:
            logger.error(f"Failed to route message to {agent_name}: {e}")
            return None
