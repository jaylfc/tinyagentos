"""Tests for temporal boosting."""

from tinyagentos.temporal_boost import classify_temporal_query, temporal_rerank


def test_ordering_first():
    r = classify_temporal_query("Which event happened first?")
    assert r["is_temporal"]
    assert r["needs_ordering"]


def test_ordering_before():
    r = classify_temporal_query("How many days before the meeting?")
    assert r["is_temporal"]
    assert r["needs_ordering"]


def test_duration():
    r = classify_temporal_query("How many days did it take?")
    assert r["is_temporal"]
    assert r["needs_duration"]


def test_when():
    r = classify_temporal_query("When did I start the project?")
    assert r["is_temporal"]
    assert r["needs_when"]


def test_not_temporal():
    r = classify_temporal_query("What is my favorite color?")
    assert not r["is_temporal"]


def test_rerank_boosts_temporal():
    results = [
        {"text": "I like blue", "similarity": 0.8},
        {"text": "On March 5th I started the project", "similarity": 0.75},
    ]
    reranked = temporal_rerank(results, "When did I start the project?", boost_factor=0.3)
    # The result with a date should be boosted above the non-temporal one
    assert reranked[0]["text"].startswith("On March")


def test_rerank_no_change_non_temporal():
    results = [
        {"text": "First item", "similarity": 0.9},
        {"text": "Second item", "similarity": 0.8},
    ]
    original_order = [r["text"] for r in results]
    reranked = temporal_rerank(results, "What color do I like?")
    assert [r["text"] for r in reranked] == original_order
