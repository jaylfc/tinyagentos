from tinyagentos.config import normalize_agent


def test_normalize_agent_adds_persona_fields_with_defaults():
    agent = {"name": "atlas", "display_name": "Atlas", "framework": "openclaw"}
    normalize_agent(agent)
    assert agent["soul_md"] == ""
    assert agent["agent_md"] == ""
    assert agent["memory_plugin"] == "taosmd"
    assert agent["source_persona_id"] is None
    assert agent["migrated_to_v2_personas"] is False


def test_normalize_agent_preserves_existing_persona_fields():
    agent = {
        "name": "atlas", "display_name": "Atlas", "framework": "openclaw",
        "soul_md": "You are Atlas", "agent_md": "Always use tools",
        "memory_plugin": "none", "source_persona_id": "builtin:research",
        "migrated_to_v2_personas": True,
    }
    normalize_agent(agent)
    assert agent["soul_md"] == "You are Atlas"
    assert agent["agent_md"] == "Always use tools"
    assert agent["memory_plugin"] == "none"
    assert agent["source_persona_id"] == "builtin:research"
    assert agent["migrated_to_v2_personas"] is True
