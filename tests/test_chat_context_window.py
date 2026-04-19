from tinyagentos.chat.context_window import build_context_window, estimate_tokens


def _msg(author, content, kind="user"):
    return {"author_id": author, "author_type": kind, "content": content}


def test_build_preserves_order_oldest_first():
    msgs = [_msg("user", "a"), _msg("tom", "b", "agent"), _msg("user", "c")]
    ctx = build_context_window(msgs, limit=20, max_tokens=1000)
    assert [m["content"] for m in ctx] == ["a", "b", "c"]


def test_build_skips_system_messages():
    msgs = [_msg("user", "hi"), _msg("system", "/lively enabled", "system"),
            _msg("tom", "yo", "agent")]
    ctx = build_context_window(msgs, limit=20, max_tokens=1000)
    assert [m["content"] for m in ctx] == ["hi", "yo"]


def test_build_applies_limit_dropping_oldest():
    msgs = [_msg("user", str(i)) for i in range(30)]
    ctx = build_context_window(msgs, limit=20, max_tokens=100000)
    assert len(ctx) == 20
    assert ctx[0]["content"] == "10"
    assert ctx[-1]["content"] == "29"


def test_build_applies_token_budget():
    long = "x" * 2000
    msgs = [_msg("user", long), _msg("tom", long, "agent"), _msg("user", long)]
    ctx = build_context_window(msgs, limit=20, max_tokens=800)
    assert sum(estimate_tokens(m["content"]) for m in ctx) <= 800


def test_build_empty():
    assert build_context_window([], limit=20, max_tokens=1000) == []


def test_estimate_tokens_4chars_per_token():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 100) == 25
