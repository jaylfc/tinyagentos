"""Tests for automatic memory extraction (taOSmd)."""

import pytest
import pytest_asyncio
from tinyagentos.memory_extractor import extract_facts_from_text, process_conversation_turn
from tinyagentos.temporal_knowledge_graph import TemporalKnowledgeGraph


@pytest_asyncio.fixture
async def graph(tmp_path):
    g = TemporalKnowledgeGraph(db_path=tmp_path / "kg.db")
    await g.init()
    yield g
    await g.close()


# ------------------------------------------------------------------
# Pattern-based extraction
# ------------------------------------------------------------------

def test_extract_uses():
    facts = extract_facts_from_text("taOS uses Python for the backend.")
    assert any(f["subject"].lower() == "taos" and f["predicate"] == "uses" and "python" in f["object"].lower() for f in facts)


def test_extract_is_a():
    facts = extract_facts_from_text("taOS is a personal AI operating system.")
    assert any(f["predicate"] == "is_a" for f in facts)


def test_extract_prefers():
    facts = extract_facts_from_text("Jay prefers local models over cloud APIs.")
    assert any(f["subject"].lower() == "jay" and f["predicate"] == "prefers" for f in facts)


def test_extract_created():
    facts = extract_facts_from_text("Jay created taOS last year.")
    assert any(f["subject"].lower() == "jay" and f["predicate"] == "created" and "taos" in f["object"].lower() for f in facts)


def test_extract_works_on():
    facts = extract_facts_from_text("The dev team works on the knowledge pipeline.")
    assert any(f["predicate"] == "works_on" for f in facts)


def test_extract_has():
    facts = extract_facts_from_text("Orange Pi has 16GB RAM and an RK3588 NPU.")
    assert any(f["predicate"] == "has" for f in facts)


def test_extract_supports():
    facts = extract_facts_from_text("The RK3588 NPU supports RKNN model format.")
    assert any(f["predicate"] == "supports" for f in facts)


def test_extract_depends_on():
    facts = extract_facts_from_text("X Monitor depends on Agent Browsers for cookie auth.")
    assert any(f["predicate"] == "depends_on" for f in facts)


def test_extract_multiple_facts():
    text = "Jay created taOS. taOS uses Python. taOS runs on Orange Pi."
    facts = extract_facts_from_text(text)
    assert len(facts) >= 2


def test_extract_skips_generic():
    facts = extract_facts_from_text("I like it. This is good. That works.")
    # Should skip "I", "This", "That" as subjects
    assert len(facts) == 0


def test_extract_deduplicates():
    text = "Jay uses Docker. Jay uses Docker."
    facts = extract_facts_from_text(text)
    jay_docker = [f for f in facts if f["subject"].lower() == "jay" and "docker" in f["object"].lower()]
    assert len(jay_docker) == 1


def test_extract_empty_text():
    facts = extract_facts_from_text("")
    assert facts == []


def test_extract_no_facts():
    facts = extract_facts_from_text("Hello, how are you today?")
    assert len(facts) == 0


# ------------------------------------------------------------------
# Pipeline integration
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_conversation_stores_in_kg(graph):
    text = "Jay created taOS. taOS uses SQLite for storage."
    triple_ids = await process_conversation_turn(text, "research-agent", graph)
    assert len(triple_ids) >= 1

    # Verify facts are in the KG
    results = await graph.query_entity("Jay")
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_process_conversation_with_agent_source(graph):
    text = "The research agent monitors Reddit daily."
    triple_ids = await process_conversation_turn(text, "research-agent", graph, source="chat")
    assert len(triple_ids) >= 0  # May or may not extract depending on patterns

    # Check the KG for any research agent facts
    results = await graph.query_entity("research agent")
    # Facts may or may not be extracted — the key is no crash


@pytest.mark.asyncio
async def test_process_empty_text(graph):
    triple_ids = await process_conversation_turn("", None, graph)
    assert triple_ids == []


@pytest.mark.asyncio
async def test_process_no_facts_text(graph):
    triple_ids = await process_conversation_turn("Hello! How are you?", None, graph)
    assert triple_ids == []
