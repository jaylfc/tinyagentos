import time
import pytest
import pytest_asyncio
from tinyagentos.temporal_knowledge_graph import (
    TemporalKnowledgeGraph,
    classify_memory_type,
)


@pytest_asyncio.fixture
async def graph(tmp_path):
    g = TemporalKnowledgeGraph(db_path=tmp_path / "kg.db")
    await g.init()
    yield g
    await g.close()


# ------------------------------------------------------------------
# Entity CRUD
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_and_get_entity(graph):
    eid = await graph.add_entity("Jay", entity_type="person")
    assert eid == "jay"
    entity = await graph.get_entity("Jay")
    assert entity is not None
    assert entity["name"] == "Jay"
    assert entity["type"] == "person"


@pytest.mark.asyncio
async def test_entity_id_normalisation(graph):
    id1 = await graph.add_entity("Orange Pi 5 Plus")
    id2 = await graph.add_entity("orange pi 5 plus")
    assert id1 == id2 == "orange-pi-5-plus"


@pytest.mark.asyncio
async def test_list_entities_by_type(graph):
    await graph.add_entity("Jay", entity_type="person")
    await graph.add_entity("taOS", entity_type="project")
    await graph.add_entity("QMD", entity_type="project")
    projects = await graph.list_entities(entity_type="project")
    assert len(projects) == 2
    all_entities = await graph.list_entities()
    assert len(all_entities) == 3


# ------------------------------------------------------------------
# Triple CRUD
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_and_query_triple(graph):
    tid = await graph.add_triple("Jay", "works_on", "taOS", source="test")
    assert tid is not None
    results = await graph.query_entity("Jay")
    assert len(results) == 1
    assert results[0]["predicate"] == "works_on"
    assert results[0]["object_name"] == "taOS"
    assert results[0]["current"] is True


@pytest.mark.asyncio
async def test_duplicate_triple_returns_existing_id(graph):
    id1 = await graph.add_triple("Jay", "works_on", "taOS")
    id2 = await graph.add_triple("Jay", "works_on", "taOS")
    assert id1 == id2


@pytest.mark.asyncio
async def test_invalidate_triple(graph):
    tid = await graph.add_triple("Jay", "works_on", "OldProject")
    ok = await graph.invalidate(tid)
    assert ok is True
    # Should not appear in current query
    results = await graph.query_entity("Jay")
    assert len(results) == 0


@pytest.mark.asyncio
async def test_temporal_query(graph):
    past = time.time() - 86400  # yesterday
    now = time.time()
    # Add a fact that was true yesterday but ended
    tid = await graph.add_triple("Jay", "works_on", "ProjectA", valid_from=past)
    await graph.invalidate(tid, ended_at=past + 3600)
    # Add a current fact
    await graph.add_triple("Jay", "works_on", "ProjectB", valid_from=now - 100)
    # Query as of now — should see ProjectB only
    current = await graph.query_entity("Jay", as_of=now)
    assert len(current) == 1
    assert current[0]["object_name"] == "ProjectB"
    # Query as of yesterday — should see ProjectA
    yesterday = await graph.query_entity("Jay", as_of=past + 1800)
    assert len(yesterday) == 1
    assert yesterday[0]["object_name"] == "ProjectA"


@pytest.mark.asyncio
async def test_update_fact(graph):
    await graph.add_triple("Jay", "works_on", "ProjectA")
    new_tid = await graph.update_fact("Jay", "works_on", "ProjectA", "ProjectB")
    assert new_tid is not None
    results = await graph.query_entity("Jay")
    assert len(results) == 1
    assert results[0]["object_name"] == "ProjectB"


@pytest.mark.asyncio
async def test_query_by_direction(graph):
    await graph.add_triple("Jay", "manages", "ResearchAgent")
    outgoing = await graph.query_entity("Jay", direction="outgoing")
    assert len(outgoing) == 1
    incoming = await graph.query_entity("ResearchAgent", direction="incoming")
    assert len(incoming) == 1
    assert incoming[0]["predicate"] == "manages"


@pytest.mark.asyncio
async def test_query_predicate(graph):
    await graph.add_triple("Jay", "uses", "taOS")
    await graph.add_triple("Alice", "uses", "taOS")
    results = await graph.query_predicate("uses")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_timeline(graph):
    await graph.add_triple("Jay", "created", "taOS", valid_from=time.time() - 1000)
    await graph.add_triple("Jay", "added", "Library", valid_from=time.time() - 500)
    await graph.add_triple("Jay", "added", "Reddit", valid_from=time.time() - 100)
    tl = await graph.timeline("Jay")
    assert len(tl) == 3
    assert tl[0]["object_name"] == "Reddit"  # newest first


@pytest.mark.asyncio
async def test_stats(graph):
    await graph.add_triple("A", "knows", "B")
    await graph.add_triple("B", "knows", "C")
    stats = await graph.stats()
    assert stats["entities"] == 3
    assert stats["triples"] == 2
    assert stats["active_triples"] == 2


# ------------------------------------------------------------------
# Memory type classification
# ------------------------------------------------------------------

def test_classify_fact():
    assert classify_memory_type("taOS is a personal AI operating system") == "fact"

def test_classify_preference():
    assert classify_memory_type("I always prefer to use local models") == "preference"

def test_classify_decision():
    assert classify_memory_type("We decided to go with Docker because of isolation") == "decision"

def test_classify_event():
    assert classify_memory_type("The v2.0 release launched yesterday") == "event"

def test_classify_discovery():
    assert classify_memory_type("I just realized the NPU can handle batched inference") == "discovery"

def test_classify_fallback():
    assert classify_memory_type("xyz abc 123") == "fact"  # fallback to fact


# ------------------------------------------------------------------
# Contradiction detection
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detect_contradiction_singular_predicate(graph):
    await graph.add_triple("Jay", "works_on", "ProjectA")
    contradictions = await graph.detect_contradictions("Jay", "works_on", "ProjectB")
    assert len(contradictions) == 1
    assert contradictions[0]["object_name"] == "ProjectA"


@pytest.mark.asyncio
async def test_no_contradiction_non_singular_predicate(graph):
    await graph.add_triple("Jay", "uses", "Python")
    contradictions = await graph.detect_contradictions("Jay", "uses", "React")
    assert len(contradictions) == 0  # "uses" is not singular — you can use multiple things


@pytest.mark.asyncio
async def test_no_contradiction_same_object(graph):
    await graph.add_triple("Jay", "works_on", "taOS")
    contradictions = await graph.detect_contradictions("Jay", "works_on", "taOS")
    assert len(contradictions) == 0  # Same fact, not a contradiction


@pytest.mark.asyncio
async def test_add_with_auto_resolve(graph):
    await graph.add_triple("Jay", "works_on", "ProjectA")
    result = await graph.add_triple_with_contradiction_check(
        "Jay", "works_on", "ProjectB", auto_resolve=True,
    )
    assert result["contradictions_found"] == 1
    assert result["contradictions_resolved"] == 1
    # Old triple should be invalidated
    current = await graph.query_entity("Jay")
    objects = [r["object_name"] for r in current]
    assert "ProjectB" in objects
    assert "ProjectA" not in objects


@pytest.mark.asyncio
async def test_add_without_auto_resolve(graph):
    await graph.add_triple("Jay", "works_on", "ProjectA")
    result = await graph.add_triple_with_contradiction_check(
        "Jay", "works_on", "ProjectB", auto_resolve=False,
    )
    assert result["contradictions_found"] == 1
    assert result["contradictions_resolved"] == 0
    # Both triples should still be active
    current = await graph.query_entity("Jay")
    objects = [r["object_name"] for r in current]
    assert "ProjectA" in objects
    assert "ProjectB" in objects
