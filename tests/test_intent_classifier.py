"""Tests for intent-aware retrieval planning."""

from tinyagentos.intent_classifier import classify_intent, get_search_strategy, INTENT_FACTUAL, INTENT_RECENT, INTENT_PREFERENCE, INTENT_TECHNICAL, INTENT_EXPLORATORY, INTENT_RELATIONAL


def test_factual_what_is():
    assert classify_intent("What is taOS?") == INTENT_FACTUAL

def test_factual_who():
    assert classify_intent("Who created taOS?") == INTENT_FACTUAL

def test_factual_how_many():
    assert classify_intent("How many apps does taOS have?") == INTENT_FACTUAL

def test_factual_runs_on():
    assert classify_intent("What hardware does taOS run on?") == INTENT_FACTUAL

def test_recent_yesterday():
    assert classify_intent("What happened yesterday?") == INTENT_RECENT

def test_recent_latest():
    assert classify_intent("What are the latest updates?") == INTENT_RECENT

def test_recent_changed():
    assert classify_intent("What changed recently?") == INTENT_RECENT

def test_preference_prefer():
    assert classify_intent("What does Jay prefer for inference?") == INTENT_PREFERENCE

def test_preference_usually():
    assert classify_intent("How does Jay usually deploy models?") == INTENT_PREFERENCE

def test_technical_how_works():
    assert classify_intent("How does the knowledge pipeline work?") == INTENT_TECHNICAL

def test_technical_architecture():
    assert classify_intent("Explain the taOS architecture") == INTENT_TECHNICAL

def test_relational_depends():
    assert classify_intent("What does X Monitor depend on?") == INTENT_RELATIONAL

def test_relational_manages():
    assert classify_intent("Who manages the research agent?") == INTENT_RELATIONAL

def test_relational_monitors():
    assert classify_intent("What does the research agent monitor?") == INTENT_RELATIONAL

def test_exploratory_default():
    assert classify_intent("Tell me about Docker") == INTENT_EXPLORATORY

def test_exploratory_vague():
    assert classify_intent("anything interesting?") == INTENT_EXPLORATORY

def test_strategy_factual_uses_kg():
    s = get_search_strategy("What is taOS?")
    assert s["intent"] == INTENT_FACTUAL
    assert s["primary"] == "kg"
    assert s["kg_weight"] == 1.0

def test_strategy_recent_uses_archive():
    s = get_search_strategy("What happened yesterday?")
    assert s["intent"] == INTENT_RECENT
    assert s["primary"] == "archive"
    assert s["archive_weight"] == 1.0

def test_strategy_technical_uses_qmd():
    s = get_search_strategy("How does the pipeline work?")
    assert s["intent"] == INTENT_TECHNICAL
    assert s["primary"] == "qmd"
    assert s["qmd_weight"] == 1.0

def test_strategy_relational_uses_kg():
    s = get_search_strategy("What does X depend on?")
    assert s["intent"] == INTENT_RELATIONAL
    assert s["primary"] == "kg"
