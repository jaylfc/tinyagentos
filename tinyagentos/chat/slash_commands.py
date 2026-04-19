"""Slash-command registry for chat channels.

Commands: mute, unmute, leave, summon, quiet, lively, hops, cooldown,
topic, rename, help. Unknown commands fall through (parse_slash returns
None). Bad arguments return a SlashResult with a user-facing error message
and no mutation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SLASH_RE = re.compile(r"^/([A-Za-z][A-Za-z_-]*)(?:\s+(.*))?$")


@dataclass(frozen=True)
class SlashResult:
    system_text: str


def parse_slash(content: str) -> tuple[str | None, str | None]:
    if not content or not content.startswith("/"):
        return None, None
    first_line = content.split("\n", 1)[0].strip()
    m = _SLASH_RE.match(first_line)
    if not m:
        return None, None
    cmd = m.group(1).lower()
    args = (m.group(2) or "").strip()
    if cmd not in _COMMANDS:
        return None, None
    return cmd, args


def _strip_at(s: str) -> str:
    s = s.strip()
    if s.startswith("@"):
        s = s[1:]
    return s


async def _cmd_lively(args, channel_id, author_id, author_type, state):
    await state.chat_channels.set_response_mode(channel_id, "lively")
    return SlashResult(f"lively mode enabled by @{author_id}")


async def _cmd_quiet(args, channel_id, author_id, author_type, state):
    await state.chat_channels.set_response_mode(channel_id, "quiet")
    return SlashResult(f"quiet mode enabled by @{author_id}")


async def _cmd_mute(args, channel_id, author_id, author_type, state):
    slug = _strip_at(args)
    if not slug:
        return SlashResult("/mute @<slug> — missing agent slug")
    known = {a.get("name") for a in getattr(state.config, "agents", []) or []}
    if slug not in known:
        return SlashResult(f"unknown agent: {slug}")
    await state.chat_channels.mute_agent(channel_id, slug)
    return SlashResult(f"@{slug} muted in this channel by @{author_id}")


async def _cmd_unmute(args, channel_id, author_id, author_type, state):
    slug = _strip_at(args)
    if not slug:
        return SlashResult("/unmute @<slug> — missing agent slug")
    await state.chat_channels.unmute_agent(channel_id, slug)
    return SlashResult(f"@{slug} unmuted in this channel by @{author_id}")


async def _cmd_leave(args, channel_id, author_id, author_type, state):
    await state.chat_channels.remove_member(channel_id, author_id)
    return SlashResult(f"@{author_id} left this channel")


async def _cmd_summon(args, channel_id, author_id, author_type, state):
    slug = _strip_at(args)
    known = {a.get("name") for a in getattr(state.config, "agents", []) or []}
    if slug not in known:
        return SlashResult(f"unknown agent: {slug}")
    await state.chat_channels.add_member(channel_id, slug)
    return SlashResult(f"@{slug} summoned to this channel by @{author_id}")


async def _cmd_hops(args, channel_id, author_id, author_type, state):
    try:
        n = int(args.strip())
        if not 1 <= n <= 10:
            raise ValueError
    except ValueError:
        return SlashResult("/hops N — N must be 1..10")
    await state.chat_channels.set_max_hops(channel_id, n)
    return SlashResult(f"max_hops set to {n} by @{author_id}")


async def _cmd_cooldown(args, channel_id, author_id, author_type, state):
    raw = args.strip().rstrip("s")
    try:
        n = int(raw)
        if not 0 <= n <= 60:
            raise ValueError
    except ValueError:
        return SlashResult("/cooldown Ns — N must be 0..60")
    await state.chat_channels.set_cooldown_seconds(channel_id, n)
    return SlashResult(f"cooldown set to {n}s by @{author_id}")


async def _cmd_topic(args, channel_id, author_id, author_type, state):
    await state.chat_channels.update_channel(channel_id, topic=args)
    return SlashResult(f"topic updated by @{author_id}")


async def _cmd_rename(args, channel_id, author_id, author_type, state):
    name = args.strip()
    if not name:
        return SlashResult("/rename <name> — missing name")
    await state.chat_channels.update_channel(channel_id, name=name)
    return SlashResult(f"channel renamed to '{name}' by @{author_id}")


async def _cmd_help(args, channel_id, author_id, author_type, state):
    lines = [
        "Slash commands in this channel:",
        "  /mute @<slug>      mute an agent",
        "  /unmute @<slug>    unmute an agent",
        "  /leave             leave this channel",
        "  /summon @<slug>    add an agent to this channel",
        "  /quiet             switch to quiet mode (respond only when @mentioned)",
        "  /lively            switch to lively mode (agents decide per message)",
        "  /hops N            set max hops-since-user (1..10)",
        "  /cooldown Ns       set per-agent cooldown (0..60s)",
        "  /topic <text>      set channel topic",
        "  /rename <name>     rename channel",
        "  /help              show this list",
    ]
    return SlashResult("\n".join(lines))


_COMMANDS = {
    "mute":     _cmd_mute,
    "unmute":   _cmd_unmute,
    "leave":    _cmd_leave,
    "summon":   _cmd_summon,
    "quiet":    _cmd_quiet,
    "lively":   _cmd_lively,
    "hops":     _cmd_hops,
    "cooldown": _cmd_cooldown,
    "topic":    _cmd_topic,
    "rename":   _cmd_rename,
    "help":     _cmd_help,
}


async def dispatch(
    command: str, args: str, channel_id: str,
    author_id: str, author_type: str, state,
) -> SlashResult:
    handler = _COMMANDS.get(command)
    if handler is None:
        return SlashResult(f"unknown command: /{command}")
    return await handler(args, channel_id, author_id, author_type, state)
