"""Tests for preference extraction."""

from tinyagentos.preference_extractor import extract_preferences, generate_synthetic_preference_docs


def test_direct_preference():
    prefs = extract_preferences("I prefer running local models over cloud APIs.")
    assert len(prefs) >= 1
    assert any("local models" in p["synthetic_doc"].lower() for p in prefs)


def test_comparative():
    prefs = extract_preferences("I find Postgres more reliable than MySQL.")
    assert len(prefs) >= 1
    assert any("postgres" in p["synthetic_doc"].lower() for p in prefs)


def test_habitual():
    prefs = extract_preferences("I always use Docker for deployments.")
    assert len(prefs) >= 1
    assert any("docker" in p["synthetic_doc"].lower() for p in prefs)


def test_negative():
    prefs = extract_preferences("I don't like using cloud services for sensitive data.")
    assert len(prefs) >= 1
    assert any("negative" in p["valence"] or "avoidance" in p["valence"] or "dislikes" in p["synthetic_doc"].lower() for p in prefs)


def test_endorsement():
    prefs = extract_preferences("I find SQLite reliable for embedded databases.")
    assert len(prefs) >= 1
    assert any("sqlite" in p["synthetic_doc"].lower() for p in prefs)


def test_over_pattern():
    prefs = extract_preferences("I choose Python over JavaScript for backend work.")
    assert len(prefs) >= 1


def test_no_preferences():
    prefs = extract_preferences("The weather is nice today.")
    assert len(prefs) == 0


def test_synthetic_docs():
    docs = generate_synthetic_preference_docs("I prefer hiking over swimming. I always use sunscreen.")
    assert len(docs) >= 1
    assert all(doc.startswith("User preference:") for doc in docs)


def test_multiple_preferences():
    text = "I like Python for scripting. I prefer VSCode over Vim. I always use dark mode."
    prefs = extract_preferences(text)
    assert len(prefs) >= 2
