import pytest
from unittest.mock import AsyncMock, MagicMock

from tinyagentos.chat.slash_commands import (
    parse_slash,
    dispatch,
    SlashResult,
)


def test_parse_slash_recognises_command():
    cmd, args = parse_slash("/lively")
    assert cmd == "lively" and args == ""


def test_parse_slash_with_args():
    cmd, args = parse_slash("/mute @tom please")
    assert cmd == "mute" and args == "@tom please"


def test_parse_slash_multiline_only_first_line():
    cmd, args = parse_slash("/topic New topic\nline two")
    assert cmd == "topic" and args == "New topic"


def test_parse_slash_non_command_returns_none():
    assert parse_slash("hello /lively there") == (None, None)
    assert parse_slash("/path/to/file") == (None, None)
    assert parse_slash("/   space") == (None, None)


@pytest.mark.asyncio
async def test_dispatch_lively_sets_mode():
    chs = MagicMock()
    chs.set_response_mode = AsyncMock()
    chs.get_channel = AsyncMock(return_value={"id": "c1", "settings": {}})
    state = MagicMock(chat_channels=chs)
    r = await dispatch("lively", "", "c1", "user", "user", state)
    assert isinstance(r, SlashResult)
    chs.set_response_mode.assert_awaited_once_with("c1", "lively")
    assert "lively" in r.system_text.lower()


@pytest.mark.asyncio
async def test_dispatch_hops_bad_arg():
    state = MagicMock()
    r = await dispatch("hops", "abc", "c1", "user", "user", state)
    assert "1..10" in r.system_text


@pytest.mark.asyncio
async def test_dispatch_mute_unknown_agent_errors():
    state = MagicMock()
    state.config = MagicMock()
    state.config.agents = [{"name": "tom"}]
    chs = MagicMock(); chs.mute_agent = AsyncMock()
    state.chat_channels = chs
    r = await dispatch("mute", "@unknown", "c1", "user", "user", state)
    assert "unknown" in r.system_text.lower() or "not found" in r.system_text.lower()
    chs.mute_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_help_lists_all_commands():
    state = MagicMock()
    r = await dispatch("help", "", "c1", "user", "user", state)
    for cmd in ["mute", "unmute", "leave", "summon", "quiet", "lively",
                "hops", "cooldown", "topic", "rename", "help"]:
        assert f"/{cmd}" in r.system_text
