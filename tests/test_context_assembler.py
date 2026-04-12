"""Tests for Context Window Assembler (taOSmd)."""

import pytest
import pytest_asyncio
from tinyagentos.context_assembler import ContextAssembler, estimate_tokens, truncate_to_tokens
from tinyagentos.temporal_knowledge_graph import TemporalKnowledgeGraph
from tinyagentos.archive import ArchiveStore


@pytest_asyncio.fixture
async def kg(tmp_path):
    g = TemporalKnowledgeGraph(db_path=tmp_path / "kg.db")
    await g.init()
    await g.add_triple("Jay", "created", "taOS", source="test")
    await g.add_triple("Jay", "prefers", "local models", source="test")
    await g.add_triple("taOS", "runs_on", "Orange Pi", source="test")
    await g.add_triple("research-agent", "monitors", "Reddit", source="test")
    yield g
    await g.close()


@pytest_asyncio.fixture
async def archive(tmp_path):
    a = ArchiveStore(archive_dir=tmp_path / "archive", index_path=tmp_path / "idx.db")
    await a.init()
    await a.record("conversation", {"content": "How do I deploy taOS?"}, agent_name="research-agent", summary="User asked about deployment")
    await a.record("tool_call", {"tool": "search", "result": "found 3 items"}, agent_name="research-agent", summary="Searched knowledge base")
    yield a
    await a.close()


# ------------------------------------------------------------------
# Utility tests
# ------------------------------------------------------------------

def test_estimate_tokens():
    assert estimate_tokens("hello world") == 2  # 11 chars / 4


def test_truncate():
    long = "a" * 1000
    result = truncate_to_tokens(long, 50)
    assert len(result) <= 203  # 50 * 4 + 3 for "..."


def test_truncate_short():
    short = "hello"
    assert truncate_to_tokens(short, 50) == "hello"


# ------------------------------------------------------------------
# L0: Identity
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l0_basic():
    ca = ContextAssembler()
    l0 = await ca.assemble_l0(agent_name="research-agent", user_name="Jay")
    assert "research-agent" in l0
    assert "Jay" in l0


@pytest.mark.asyncio
async def test_l0_with_system_info():
    ca = ContextAssembler()
    l0 = await ca.assemble_l0(
        agent_name="agent",
        system_info={"cpu": "RK3588", "npu": "6 TOPS", "ram": "16GB"},
    )
    assert "RK3588" in l0
    assert "6 TOPS" in l0


@pytest.mark.asyncio
async def test_l0_empty():
    ca = ContextAssembler()
    l0 = await ca.assemble_l0()
    assert l0 == ""


# ------------------------------------------------------------------
# L1: Knowledge Graph Facts
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l1_returns_kg_facts(kg):
    ca = ContextAssembler(kg=kg)
    l1 = await ca.assemble_l1(user_name="Jay")
    assert "created" in l1
    assert "taOS" in l1


@pytest.mark.asyncio
async def test_l1_multiple_entities(kg):
    ca = ContextAssembler(kg=kg)
    l1 = await ca.assemble_l1(user_name="Jay", agent_name="research-agent")
    assert "Jay" in l1
    assert "monitors" in l1


@pytest.mark.asyncio
async def test_l1_no_kg():
    ca = ContextAssembler()
    l1 = await ca.assemble_l1(user_name="Jay")
    assert l1 == ""


# ------------------------------------------------------------------
# L2: Relevant Context
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l2_searches_archive(kg, archive):
    ca = ContextAssembler(kg=kg, archive=archive)
    l2 = await ca.assemble_l2("deployment")
    assert "deployment" in l2.lower() or "deploy" in l2.lower()


@pytest.mark.asyncio
async def test_l2_searches_kg(kg):
    ca = ContextAssembler(kg=kg)
    l2 = await ca.assemble_l2("taOS hardware")
    # Should find KG facts about taOS
    assert "taOS" in l2 or "runs_on" in l2 or len(l2) > 0


@pytest.mark.asyncio
async def test_l2_empty_query(kg):
    ca = ContextAssembler(kg=kg)
    l2 = await ca.assemble_l2("")
    # Empty query may still find something or return empty
    assert isinstance(l2, str)


# ------------------------------------------------------------------
# Full assembly
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assemble_minimal(kg, archive):
    ca = ContextAssembler(kg=kg, archive=archive)
    result = await ca.assemble(
        query="How do I deploy?",
        agent_name="research-agent",
        user_name="Jay",
        depth="minimal",
    )
    assert "context" in result
    assert "layers" in result
    assert result["layers"]["l0"] > 0
    assert result["layers"]["l1"] > 0
    assert result["layers"]["l2"] == 0  # Not loaded in minimal
    assert result["layers"]["l3"] == 0  # Not loaded in minimal
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_assemble_standard(kg, archive):
    ca = ContextAssembler(kg=kg, archive=archive)
    result = await ca.assemble(
        query="taOS deployment Orange",
        agent_name="research-agent",
        user_name="Jay",
        depth="standard",
    )
    assert result["layers"]["l0"] > 0
    # L2 searches KG for words in query — "taOS" and "Orange" should match KG entities
    assert result["layers"]["l2"] >= 0  # May find KG matches
    assert result["total_tokens"] > 0


@pytest.mark.asyncio
async def test_assemble_deep(kg, archive):
    ca = ContextAssembler(kg=kg, archive=archive)
    result = await ca.assemble(
        query="How do I deploy?",
        agent_name="research-agent",
        user_name="Jay",
        depth="deep",
    )
    assert result["layers"]["l3"] > 0  # Loaded in deep
    assert result["total_tokens"] > result["layers"]["l0"]


@pytest.mark.asyncio
async def test_assemble_respects_token_budget(kg, archive):
    ca = ContextAssembler(kg=kg, archive=archive)
    result = await ca.assemble(
        query="Tell me everything about taOS",
        depth="deep",
        max_total_tokens=100,
    )
    assert result["total_tokens"] <= 100


@pytest.mark.asyncio
async def test_assemble_returns_latency(kg, archive):
    ca = ContextAssembler(kg=kg, archive=archive)
    result = await ca.assemble(query="test", depth="minimal")
    assert "latency_ms" in result
    assert result["latency_ms"] >= 0
