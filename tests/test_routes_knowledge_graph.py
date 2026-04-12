"""Route-level tests for the Temporal Knowledge Graph API (taOSmd)."""

import time
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tinyagentos.temporal_knowledge_graph import TemporalKnowledgeGraph
from tinyagentos.routes.knowledge_graph import router


@pytest_asyncio.fixture
async def kg_client(tmp_path):
    graph = TemporalKnowledgeGraph(db_path=tmp_path / "kg.db")
    await graph.init()

    app = FastAPI()
    app.state.knowledge_graph = graph
    app.include_router(router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    await graph.close()


# ------------------------------------------------------------------
# Entity endpoints
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_entity(kg_client):
    resp = await kg_client.post("/api/kg/entities", json={"name": "Jay", "type": "person"})
    assert resp.status_code == 200
    assert resp.json()["id"] == "jay"


@pytest.mark.asyncio
async def test_list_entities(kg_client):
    await kg_client.post("/api/kg/entities", json={"name": "Jay", "type": "person"})
    await kg_client.post("/api/kg/entities", json={"name": "taOS", "type": "project"})
    resp = await kg_client.get("/api/kg/entities")
    assert resp.status_code == 200
    assert resp.json()["count"] == 2


@pytest.mark.asyncio
async def test_list_entities_by_type(kg_client):
    await kg_client.post("/api/kg/entities", json={"name": "Jay", "type": "person"})
    await kg_client.post("/api/kg/entities", json={"name": "taOS", "type": "project"})
    resp = await kg_client.get("/api/kg/entities?type=project")
    assert resp.json()["count"] == 1


@pytest.mark.asyncio
async def test_get_entity(kg_client):
    await kg_client.post("/api/kg/entities", json={"name": "Jay", "type": "person"})
    resp = await kg_client.get("/api/kg/entities/Jay")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Jay"


@pytest.mark.asyncio
async def test_get_entity_not_found(kg_client):
    resp = await kg_client.get("/api/kg/entities/Nobody")
    assert resp.status_code == 404


# ------------------------------------------------------------------
# Triple endpoints
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_triple(kg_client):
    resp = await kg_client.post("/api/kg/triples", json={
        "subject": "Jay",
        "predicate": "works_on",
        "object": "taOS",
        "source": "test",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert "id" in resp.json()


@pytest.mark.asyncio
async def test_invalidate_triple(kg_client):
    resp = await kg_client.post("/api/kg/triples", json={
        "subject": "Jay", "predicate": "uses", "object": "OldTool",
    })
    tid = resp.json()["id"]
    resp2 = await kg_client.post("/api/kg/triples/invalidate", json={"triple_id": tid})
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "invalidated"


@pytest.mark.asyncio
async def test_invalidate_not_found(kg_client):
    resp = await kg_client.post("/api/kg/triples/invalidate", json={"triple_id": "nonexistent"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_fact(kg_client):
    await kg_client.post("/api/kg/triples", json={
        "subject": "Jay", "predicate": "works_on", "object": "ProjectA",
    })
    resp = await kg_client.post("/api/kg/triples/update", json={
        "subject": "Jay",
        "predicate": "works_on",
        "old_object": "ProjectA",
        "new_object": "ProjectB",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "updated"
    # Verify old is gone, new is present
    q = await kg_client.get("/api/kg/query/Jay")
    results = q.json()["results"]
    objects = [r["object_name"] for r in results]
    assert "ProjectB" in objects
    assert "ProjectA" not in objects


# ------------------------------------------------------------------
# Query endpoints
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_entity(kg_client):
    await kg_client.post("/api/kg/triples", json={
        "subject": "Jay", "predicate": "manages", "object": "ResearchAgent",
    })
    resp = await kg_client.get("/api/kg/query/Jay")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert resp.json()["results"][0]["predicate"] == "manages"


@pytest.mark.asyncio
async def test_query_entity_direction(kg_client):
    await kg_client.post("/api/kg/triples", json={
        "subject": "Jay", "predicate": "manages", "object": "Agent",
    })
    outgoing = await kg_client.get("/api/kg/query/Jay?direction=outgoing")
    assert outgoing.json()["count"] == 1
    incoming = await kg_client.get("/api/kg/query/Agent?direction=incoming")
    assert incoming.json()["count"] == 1


@pytest.mark.asyncio
async def test_query_predicate(kg_client):
    await kg_client.post("/api/kg/triples", json={
        "subject": "Jay", "predicate": "uses", "object": "taOS",
    })
    await kg_client.post("/api/kg/triples", json={
        "subject": "Alice", "predicate": "uses", "object": "taOS",
    })
    resp = await kg_client.get("/api/kg/query/predicate/uses")
    assert resp.json()["count"] == 2


@pytest.mark.asyncio
async def test_timeline(kg_client):
    await kg_client.post("/api/kg/triples", json={
        "subject": "Jay", "predicate": "created", "object": "taOS",
    })
    await kg_client.post("/api/kg/triples", json={
        "subject": "Jay", "predicate": "added", "object": "Library",
    })
    resp = await kg_client.get("/api/kg/timeline?name=Jay")
    assert resp.json()["count"] == 2


@pytest.mark.asyncio
async def test_stats(kg_client):
    await kg_client.post("/api/kg/triples", json={
        "subject": "A", "predicate": "knows", "object": "B",
    })
    resp = await kg_client.get("/api/kg/stats")
    data = resp.json()
    assert data["entities"] == 2
    assert data["triples"] == 1
    assert data["active_triples"] == 1


# ------------------------------------------------------------------
# Classification
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_classify_memory(kg_client):
    resp = await kg_client.post("/api/kg/classify", json={
        "text": "We decided to go with Docker and chose it because of better isolation",
    })
    assert resp.status_code == 200
    assert resp.json()["type"] == "decision"


@pytest.mark.asyncio
async def test_classify_preference(kg_client):
    resp = await kg_client.post("/api/kg/classify", json={
        "text": "I always prefer local models over cloud APIs",
    })
    assert resp.json()["type"] == "preference"
