from __future__ import annotations
from dataclasses import dataclass, field
import time


@dataclass
class IncomingMessage:
    id: str
    from_id: str
    from_name: str
    platform: str  # telegram | discord | slack | email | web | webhook
    channel_id: str
    channel_name: str
    text: str
    attachments: list[dict] = field(default_factory=list)
    reply_to: str | None = None
    timestamp: float = field(default_factory=time.time)
    raw: dict = field(default_factory=dict)  # original platform payload


@dataclass
class OutgoingMessage:
    content: str = ""
    buttons: list[dict] = field(default_factory=list)  # [{label, action}]
    images: list[str] = field(default_factory=list)  # file paths or URLs
    cards: list[dict] = field(default_factory=list)
    reply_to: str | None = None
    passthrough: bool = False
    passthrough_platform: str = ""
    passthrough_payload: dict = field(default_factory=dict)


def parse_inline_hints(text: str) -> OutgoingMessage:
    """Parse inline hints like [button:Label:action] from plain text responses."""
    import re
    buttons = []
    images = []
    clean_text = text

    # Parse [button:Label:action]
    for match in re.finditer(r'\[button:([^:]+):([^\]]+)\]', text):
        buttons.append({"label": match.group(1), "action": match.group(2)})
        clean_text = clean_text.replace(match.group(0), "")

    # Parse [image:path]
    for match in re.finditer(r'\[image:([^\]]+)\]', text):
        images.append(match.group(1))
        clean_text = clean_text.replace(match.group(0), "")

    return OutgoingMessage(
        content=clean_text.strip(),
        buttons=buttons,
        images=images,
    )
