import pytest
from tinyagentos.chat.help import handle_help, KNOWN_TOPICS


def test_overview_on_empty_args():
    out = handle_help("")
    assert "chat-guide" in out.lower()
    # lists known topics
    for t in ["threads", "attachments", "mentions"]:
        assert t in out


def test_specific_topic_returns_section():
    out = handle_help("threads")
    assert "thread" in out.lower()
    assert "chat-guide" in out.lower()  # link to full guide


def test_unknown_topic_returns_generic_message():
    out = handle_help("unknownthing")
    assert "unknown" in out.lower() or "try /help" in out.lower()


def test_all_documented_topics_have_handlers():
    for t in KNOWN_TOPICS:
        out = handle_help(t)
        assert len(out) > 0
        assert "error" not in out.lower()
