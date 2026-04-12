#!/usr/bin/env python3
"""taOSmd Benchmark — Compare retrieval quality across memory layers.

Tests: Knowledge Graph alone, QMD vector search alone, and combined.
Measures: hit rate, precision, latency.

Usage: .venv/bin/python benchmarks/taosmd_benchmark.py
"""

import asyncio
import json
import time
from pathlib import Path

import httpx

BASE = "http://localhost:6969"
QMD_BASE = "http://localhost:7832"

# ------------------------------------------------------------------
# Test data: facts about a fictional but realistic project scenario
# ------------------------------------------------------------------

SEED_FACTS = [
    # Project facts
    ("Jay", "created", "taOS", "project"),
    ("Jay", "works_on", "taOS", "project"),
    ("taOS", "runs_on", "Orange Pi 5 Plus", "hardware"),
    ("taOS", "uses", "Python", "technology"),
    ("taOS", "uses", "React", "technology"),
    ("taOS", "uses", "SQLite", "technology"),
    ("taOS", "has_feature", "Knowledge Pipeline", "feature"),
    ("taOS", "has_feature", "Agent Browsers", "feature"),
    ("taOS", "has_feature", "Shortcut Registry", "feature"),

    # People
    ("Jay", "prefers", "local models", "preference"),
    ("Jay", "prefers", "NPU inference", "preference"),
    ("Jay", "manages", "research-agent", "agent"),
    ("Jay", "manages", "dev-agent", "agent"),

    # Agent facts
    ("research-agent", "monitors", "Reddit", "platform"),
    ("research-agent", "monitors", "YouTube", "platform"),
    ("dev-agent", "monitors", "GitHub", "platform"),

    # Hardware
    ("Orange Pi 5 Plus", "has", "RK3588 NPU", "hardware"),
    ("Orange Pi 5 Plus", "has", "Mali-Bifrost GPU", "hardware"),
    ("Orange Pi 5 Plus", "has", "16GB RAM", "hardware"),
    ("RK3588 NPU", "supports", "RKNN models", "technology"),
]

SEED_DOCUMENTS = [
    {
        "title": "taOS Architecture Overview",
        "content": "taOS is a personal AI operating system that runs on your own hardware. It manages AI agents, captures knowledge from platforms like Reddit, YouTube, X, and GitHub, and provides a desktop OS experience in the browser. Built with Python backend and React TypeScript frontend, using SQLite for storage and QMD for vector search.",
    },
    {
        "title": "Orange Pi 5 Plus Hardware Guide",
        "content": "The Orange Pi 5 Plus features the Rockchip RK3588 SoC with a 6 TOPS NPU, Mali-G610 MP4 GPU, and up to 16GB LPDDR4x RAM. It supports NVMe SSD storage and runs Armbian Linux. The NPU can run quantized LLMs via rkllama and RKNN models for inference tasks.",
    },
    {
        "title": "Knowledge Pipeline Design",
        "content": "The Knowledge Capture Pipeline saves content from Reddit, YouTube, X, GitHub, and web articles. Each item is downloaded, transcribed, summarised by LLM, embedded into vector search, auto-categorised, and monitored for changes. The Library App provides a unified view across all platforms.",
    },
    {
        "title": "Agent Memory and Dreaming",
        "content": "Each agent in taOS has its own memory index. The dreaming system consolidates short-term signals into long-term memory overnight. The temporal knowledge graph tracks entity relationships with validity windows, enabling point-in-time queries about what was true at any moment.",
    },
    {
        "title": "Jay's Preferences",
        "content": "Jay prefers running models locally on the NPU rather than using cloud APIs. He always uses subagent-driven development for implementation tasks. He values proper upstream contributions and never commits sensitive data like IP addresses or API keys.",
    },
]

# ------------------------------------------------------------------
# Queries with expected answers
# ------------------------------------------------------------------

QUERIES = [
    {
        "query": "What hardware does taOS run on?",
        "expected_entities": ["Orange Pi 5 Plus", "RK3588 NPU", "Mali-Bifrost GPU"],
        "expected_keywords": ["orange pi", "rk3588", "npu"],
    },
    {
        "query": "Who created taOS?",
        "expected_entities": ["Jay"],
        "expected_keywords": ["jay"],
    },
    {
        "query": "What platforms does the research agent monitor?",
        "expected_entities": ["Reddit", "YouTube"],
        "expected_keywords": ["reddit", "youtube"],
    },
    {
        "query": "What technologies does taOS use?",
        "expected_entities": ["Python", "React", "SQLite"],
        "expected_keywords": ["python", "react", "sqlite"],
    },
    {
        "query": "What does Jay prefer for model inference?",
        "expected_entities": ["local models", "NPU inference"],
        "expected_keywords": ["local", "npu", "prefer"],
    },
    {
        "query": "What features does taOS have?",
        "expected_entities": ["Knowledge Pipeline", "Agent Browsers", "Shortcut Registry"],
        "expected_keywords": ["knowledge", "pipeline", "browser", "shortcut"],
    },
    {
        "query": "What agents does Jay manage?",
        "expected_entities": ["research-agent", "dev-agent"],
        "expected_keywords": ["research", "dev", "agent"],
    },
    {
        "query": "What does the RK3588 NPU support?",
        "expected_entities": ["RKNN models"],
        "expected_keywords": ["rknn", "models"],
    },
]


async def seed_knowledge_graph(client: httpx.AsyncClient):
    """Populate the temporal knowledge graph with test facts."""
    print("  Seeding knowledge graph...")
    for subj, pred, obj, obj_type in SEED_FACTS:
        await client.post(f"{BASE}/api/kg/triples", json={
            "subject": subj,
            "predicate": pred,
            "object": obj,
            "object_type": obj_type,
            "source": "benchmark",
        })
    print(f"  -> {len(SEED_FACTS)} triples added")


async def seed_qmd_documents(client: httpx.AsyncClient):
    """Check if QMD has searchable documents. QMD uses file-based collections."""
    print("  Checking QMD collections...")
    try:
        resp = await client.get(f"{QMD_BASE}/collections", timeout=5)
        if resp.status_code == 200:
            collections = resp.json()
            total_docs = sum(c.get("doc_count", 0) for c in collections)
            coll_names = [c["name"] for c in collections]
            print(f"  -> {total_docs} documents across collections: {', '.join(coll_names)}")
            return total_docs > 0
    except Exception:
        pass
    print("  -> No collections available")
    return False


async def query_knowledge_graph(client: httpx.AsyncClient, query: str, expected_entities: list[str]) -> dict:
    """Query the KG for relevant entities."""
    t0 = time.time()
    hits = 0
    found = []

    # Try querying each expected entity to see if the KG has relevant triples
    for entity in expected_entities:
        resp = await client.get(f"{BASE}/api/kg/query/{entity}")
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                hits += 1
                found.append(entity)

    latency = time.time() - t0
    precision = hits / len(expected_entities) if expected_entities else 0
    return {
        "method": "knowledge_graph",
        "query": query,
        "hits": hits,
        "expected": len(expected_entities),
        "precision": round(precision, 2),
        "latency_ms": round(latency * 1000, 1),
        "found": found,
    }


async def query_qmd_vector(client: httpx.AsyncClient, query: str, expected_keywords: list[str]) -> dict:
    """Query QMD vector search."""
    t0 = time.time()
    try:
        resp = await client.post(f"{QMD_BASE}/vsearch", json={
            "query": query,
            "limit": 5,
            "collection": "workspace",
        }, timeout=30)
        if resp.status_code != 200:
            return {"method": "qmd_vector", "query": query, "hits": 0, "expected": len(expected_keywords),
                    "precision": 0, "latency_ms": round((time.time() - t0) * 1000, 1), "error": f"status {resp.status_code}"}

        results = resp.json().get("results", [])
        # Check how many expected keywords appear in the results
        result_text = " ".join(r.get("content", "") + " " + r.get("title", "") for r in results).lower()
        hits = sum(1 for kw in expected_keywords if kw.lower() in result_text)
    except Exception as e:
        return {"method": "qmd_vector", "query": query, "hits": 0, "expected": len(expected_keywords),
                "precision": 0, "latency_ms": round((time.time() - t0) * 1000, 1), "error": str(e)}

    latency = time.time() - t0
    precision = hits / len(expected_keywords) if expected_keywords else 0
    return {
        "method": "qmd_vector",
        "query": query,
        "hits": hits,
        "expected": len(expected_keywords),
        "precision": round(precision, 2),
        "latency_ms": round(latency * 1000, 1),
        "result_count": len(results),
    }


async def query_combined(client: httpx.AsyncClient, query: str, expected_entities: list[str], expected_keywords: list[str]) -> dict:
    """Query both KG and QMD, merge results."""
    t0 = time.time()
    all_expected = set(e.lower() for e in expected_entities) | set(k.lower() for k in expected_keywords)
    found = set()

    # KG query — try each word in the query as a potential entity
    words = query.lower().replace("?", "").split()
    for word in words:
        resp = await client.get(f"{BASE}/api/kg/query/{word}")
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            for r in results:
                for field in ("object_name", "subject_name", "predicate"):
                    if field in r:
                        found.add(r[field].lower())

    # Also try the expected entities directly
    for entity in expected_entities:
        resp = await client.get(f"{BASE}/api/kg/query/{entity}")
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            for r in results:
                for field in ("object_name", "subject_name"):
                    if field in r:
                        found.add(r[field].lower())

    # QMD vector search
    try:
        resp = await client.post(f"{QMD_BASE}/vsearch", json={
            "query": query, "limit": 5, "collection": "workspace",
        }, timeout=30)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            result_text = " ".join(r.get("content", "") + " " + r.get("title", "") for r in results).lower()
            for kw in expected_keywords:
                if kw.lower() in result_text:
                    found.add(kw.lower())
    except Exception:
        pass

    hits = sum(1 for e in all_expected if any(e in f for f in found))
    latency = time.time() - t0
    precision = hits / len(all_expected) if all_expected else 0
    return {
        "method": "combined",
        "query": query,
        "hits": hits,
        "expected": len(all_expected),
        "precision": round(precision, 2),
        "latency_ms": round(latency * 1000, 1),
    }


async def run_benchmark():
    print("=" * 60)
    print("taOSmd Retrieval Benchmark")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # Check services
        print("\nChecking services...")
        try:
            kg_resp = await client.get(f"{BASE}/api/kg/stats")
            print(f"  Knowledge Graph: OK")
        except Exception:
            print(f"  Knowledge Graph: UNAVAILABLE")
            return

        qmd_available = False
        try:
            qmd_resp = await client.get(f"{QMD_BASE}/health", timeout=5)
            if qmd_resp.status_code == 200:
                qmd_available = True
                print(f"  QMD Vector Search: OK ({qmd_resp.json().get('backend', 'unknown')})")
        except Exception:
            print(f"  QMD Vector Search: UNAVAILABLE (will benchmark KG only)")

        # Seed data
        print("\nSeeding test data...")
        await seed_knowledge_graph(client)
        qmd_seeded = False
        if qmd_available:
            qmd_seeded = await seed_qmd_documents(client)

        # Run queries
        print(f"\nRunning {len(QUERIES)} queries...\n")

        kg_scores = []
        qmd_scores = []
        combined_scores = []
        kg_latencies = []
        qmd_latencies = []
        combined_latencies = []

        for q in QUERIES:
            print(f"  Q: {q['query']}")

            # Knowledge Graph
            kg_result = await query_knowledge_graph(client, q["query"], q["expected_entities"])
            kg_scores.append(kg_result["precision"])
            kg_latencies.append(kg_result["latency_ms"])
            print(f"    KG:       {kg_result['hits']}/{kg_result['expected']} ({kg_result['precision']:.0%}) in {kg_result['latency_ms']:.0f}ms")

            # QMD Vector
            if qmd_seeded:
                qmd_result = await query_qmd_vector(client, q["query"], q["expected_keywords"])
                qmd_scores.append(qmd_result["precision"])
                qmd_latencies.append(qmd_result["latency_ms"])
                err = qmd_result.get("error", "")
                print(f"    QMD:      {qmd_result['hits']}/{qmd_result['expected']} ({qmd_result['precision']:.0%}) in {qmd_result['latency_ms']:.0f}ms{' [' + err + ']' if err else ''}")

                # Combined
                comb_result = await query_combined(client, q["query"], q["expected_entities"], q["expected_keywords"])
                combined_scores.append(comb_result["precision"])
                combined_latencies.append(comb_result["latency_ms"])
                print(f"    Combined: {comb_result['hits']}/{comb_result['expected']} ({comb_result['precision']:.0%}) in {comb_result['latency_ms']:.0f}ms")

            print()

        # Summary
        print("=" * 60)
        print("RESULTS SUMMARY")
        print("=" * 60)

        avg_kg = sum(kg_scores) / len(kg_scores) if kg_scores else 0
        avg_kg_lat = sum(kg_latencies) / len(kg_latencies) if kg_latencies else 0
        print(f"\n  Knowledge Graph (structured triples):")
        print(f"    Average precision: {avg_kg:.0%}")
        print(f"    Average latency:   {avg_kg_lat:.0f}ms")

        if qmd_scores:
            avg_qmd = sum(qmd_scores) / len(qmd_scores) if qmd_scores else 0
            avg_qmd_lat = sum(qmd_latencies) / len(qmd_latencies) if qmd_latencies else 0
            print(f"\n  QMD Vector Search (semantic embeddings):")
            print(f"    Average precision: {avg_qmd:.0%}")
            print(f"    Average latency:   {avg_qmd_lat:.0f}ms")

            avg_comb = sum(combined_scores) / len(combined_scores) if combined_scores else 0
            avg_comb_lat = sum(combined_latencies) / len(combined_latencies) if combined_latencies else 0
            print(f"\n  Combined (KG + QMD):")
            print(f"    Average precision: {avg_comb:.0%}")
            print(f"    Average latency:   {avg_comb_lat:.0f}ms")

            if avg_comb > avg_qmd:
                improvement = ((avg_comb - avg_qmd) / avg_qmd * 100) if avg_qmd > 0 else 0
                print(f"\n  -> Combined improves over QMD alone by {improvement:.0f}%")
            elif avg_comb > avg_kg:
                print(f"\n  -> Combined improves over KG alone")
            else:
                print(f"\n  -> No clear improvement from combining (may need more diverse test data)")
        else:
            print(f"\n  QMD not available — KG-only benchmark complete.")

        # KG stats
        stats = (await client.get(f"{BASE}/api/kg/stats")).json()
        print(f"\n  Knowledge Graph: {stats['entities']} entities, {stats['triples']} triples")

        print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(run_benchmark())
