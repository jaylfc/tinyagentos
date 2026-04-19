import pytest
from tinyagentos.chat.typing_registry import TypingRegistry


def test_empty_registry_returns_empty_lists():
    r = TypingRegistry()
    assert r.list("c1") == {"human": [], "agent": []}


def test_mark_human_appears_in_list():
    r = TypingRegistry()
    r.mark("c1", "jay", "human")
    assert r.list("c1")["human"] == ["jay"]
    assert r.list("c1")["agent"] == []


def test_mark_agent_appears_in_list():
    r = TypingRegistry()
    r.mark("c1", "tom", "agent")
    assert r.list("c1")["agent"] == ["tom"]


def test_clear_removes_entry():
    r = TypingRegistry()
    r.mark("c1", "tom", "agent")
    r.clear("c1", "tom")
    assert r.list("c1")["agent"] == []


def test_clear_idempotent():
    r = TypingRegistry()
    r.clear("c1", "nobody")  # must not raise


def test_different_channels_independent():
    r = TypingRegistry()
    r.mark("c1", "jay", "human")
    assert r.list("c2") == {"human": [], "agent": []}


def test_human_ttl_expires(monkeypatch):
    r = TypingRegistry(human_ttl=3, agent_ttl=45)
    t = [1000.0]
    monkeypatch.setattr("tinyagentos.chat.typing_registry._now", lambda: t[0])
    r.mark("c1", "jay", "human")
    assert r.list("c1")["human"] == ["jay"]
    t[0] = 1003.1
    assert r.list("c1")["human"] == []


def test_agent_ttl_expires(monkeypatch):
    r = TypingRegistry(human_ttl=3, agent_ttl=45)
    t = [1000.0]
    monkeypatch.setattr("tinyagentos.chat.typing_registry._now", lambda: t[0])
    r.mark("c1", "tom", "agent")
    assert r.list("c1")["agent"] == ["tom"]
    t[0] = 1045.1
    assert r.list("c1")["agent"] == []


def test_mark_refreshes_ttl(monkeypatch):
    r = TypingRegistry(human_ttl=3, agent_ttl=45)
    t = [1000.0]
    monkeypatch.setattr("tinyagentos.chat.typing_registry._now", lambda: t[0])
    r.mark("c1", "jay", "human")
    t[0] = 1002.0
    r.mark("c1", "jay", "human")  # refresh
    t[0] = 1004.0
    assert r.list("c1")["human"] == ["jay"]  # still alive (refreshed at 1002)
