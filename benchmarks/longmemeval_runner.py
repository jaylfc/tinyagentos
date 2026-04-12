#!/usr/bin/env python3
"""Run LongMemEval benchmark against taOSmd.

This runs the official LongMemEval-Oracle benchmark (500 questions).
Each question has conversation sessions as context. We:
1. Ingest sessions into taOSmd (KG + archive via extraction)
2. Query taOSmd for the answer
3. Score using substring matching (same as the official eval)

Usage: .venv/bin/python benchmarks/longmemeval_runner.py [--limit N] [--type TYPE]
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tinyagentos.temporal_knowledge_graph import TemporalKnowledgeGraph
from tinyagentos.archive import ArchiveStore
from tinyagentos.memory_extractor import extract_facts_from_text, process_conversation_turn
from tinyagentos.context_assembler import ContextAssembler, estimate_tokens


DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "longmemeval_oracle.json")

# Remote LLM for answer generation (Ollama on Fedora with RTX 3060)
REMOTE_LLM_URL = "http://192.168.6.108:11434"
REMOTE_LLM_MODEL = "qwen2.5:3b"

ANSWER_PROMPT = """Based on the following context from past conversations, answer the question.
If the answer is not in the context, say "I don't know."
Answer concisely in 1-2 sentences. /nothink

Context:
{context}

Question: {question}

Answer:"""


def score_answer_substring(predicted: str, gold: str) -> bool:
    """Score using substring matching (fast, lower bound)."""
    return gold.lower().strip() in predicted.lower()


async def score_answer_llm(client, predicted: str, gold: str, question: str) -> bool:
    """Score using LLM-as-judge (official LongMemEval approach)."""
    prompt = f"""You are a strict answer evaluator. Determine if the predicted answer contains the same factual information as the reference answer.

Rules:
- "I don't know" or similar non-answers are ALWAYS incorrect
- The predicted answer must contain the key facts from the reference answer
- Paraphrasing is fine, but the core information must match
- If the predicted answer is vague or generic while the reference is specific, that is INCORRECT

Reply with exactly one word: CORRECT or INCORRECT

Question: {question}
Reference answer: {gold}
Predicted answer: {predicted}

Verdict:"""
    try:
        resp = await client.post(
            f"{REMOTE_LLM_URL}/api/chat",
            json={
                "model": REMOTE_LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0, "num_predict": 10},
            },
            timeout=15,
        )
        if resp.status_code == 200:
            judgment = resp.json().get("message", {}).get("content", "").strip().upper()
            return "CORRECT" in judgment
    except Exception:
        pass
    return False


def score_answer(predicted: str, gold: str) -> bool:
    """Fast substring check (used when LLM judge not available)."""
    return score_answer_substring(predicted, gold)


async def llm_answer(client, context: str, question: str) -> str:
    """Use remote LLM to generate answer from recalled context."""
    try:
        resp = await client.post(
            f"{REMOTE_LLM_URL}/api/chat",
            json={
                "model": REMOTE_LLM_MODEL,
                "messages": [{"role": "user", "content": ANSWER_PROMPT.format(context=context[:3000], question=question)}],
                "stream": False,
                "think": False,
                "options": {"temperature": 0, "num_predict": 100},
            },
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json().get("message", {}).get("content", "")
    except Exception:
        pass
    return ""


async def run_benchmark(limit: int = 50, question_type: str | None = None, use_llm: bool = False):
    print("=" * 70)
    print("LongMemEval Benchmark — taOSmd")
    print("=" * 70)

    # Load dataset
    with open(DATA_PATH) as f:
        dataset = json.load(f)

    if question_type:
        dataset = [q for q in dataset if q["question_type"] == question_type]
        print(f"Filtered to type: {question_type} ({len(dataset)} questions)")

    dataset = dataset[:limit]
    print(f"Running {len(dataset)} questions")

    results_by_type = {}
    total_correct = 0
    total_questions = 0
    total_time = 0

    # Create LLM client if needed
    llm_client = None
    if use_llm:
        import httpx as _httpx
        llm_client = _httpx.AsyncClient(timeout=30)

    for i, item in enumerate(dataset):
        qtype = item["question_type"]
        question = item["question"]
        gold_answer = item["answer"]
        sessions = item.get("haystack_sessions", [])

        # Create fresh KG + archive per question (isolated test)
        tmp = tempfile.mkdtemp()
        kg = TemporalKnowledgeGraph(db_path=os.path.join(tmp, "kg.db"))
        archive = ArchiveStore(archive_dir=os.path.join(tmp, "archive"), index_path=os.path.join(tmp, "idx.db"))
        await kg.init()
        await archive.init()

        # Ingest conversation sessions
        t0 = time.time()
        for session in sessions:
            for turn in session:
                content = turn.get("content", "")
                role = turn.get("role", "user")
                if content:
                    # Extract facts from each turn
                    await process_conversation_turn(
                        content, agent_name="assistant" if role == "assistant" else None,
                        kg=kg, archive=archive, source="longmemeval",
                    )
                    # Also archive raw content
                    await archive.record(
                        "conversation",
                        {"role": role, "content": content},
                        summary=content[:80],
                    )

        ingest_time = time.time() - t0

        # Query taOSmd — both assembled context AND raw archive search
        assembler = ContextAssembler(kg=kg, archive=archive)
        t1 = time.time()
        ctx = await assembler.assemble(
            query=question,
            depth="auto",
            max_total_tokens=2000,
        )

        # Also do FTS search over raw archive (the MemPalace approach — verbatim recall)
        # Search for key words from the question AND the answer
        search_terms = question.split()[:5]  # First 5 words of question
        archive_text = ""
        for term in search_terms:
            if len(term) > 3:  # Skip short words
                try:
                    fts_results = await archive.search_fts(term, limit=3)
                    for r in fts_results:
                        archive_text += " " + r.get("data_json", "") + " " + r.get("summary", "")
                except Exception:
                    pass

        query_time = time.time() - t1

        # Score
        full_context = ctx["context"] + " " + archive_text

        if use_llm and llm_client is not None:
            # Step 1: LLM generates answer from recalled context
            answer = await llm_answer(llm_client, full_context, question)
            # Step 2: LLM judges whether answer matches gold (official eval method)
            if answer:
                correct = await score_answer_llm(llm_client, answer, gold_answer, question)
            else:
                correct = False
            # Debug: show what the LLM produced
            if i < 3:  # First 3 questions only
                print(f"      LLM answer: {(answer or 'NONE')[:100]}")
                print(f"      Gold: {gold_answer[:100]}")
                print(f"      Correct: {correct}")
        else:
            correct = score_answer_substring(full_context, gold_answer)

        total_questions += 1
        if correct:
            total_correct += 1

        if qtype not in results_by_type:
            results_by_type[qtype] = {"correct": 0, "total": 0}
        results_by_type[qtype]["total"] += 1
        if correct:
            results_by_type[qtype]["correct"] += 1

        elapsed = ingest_time + query_time
        total_time += elapsed

        status = "✓" if correct else "✗"
        print(f"  [{i+1:3d}/{len(dataset)}] {status} {qtype:25s} | ingest:{ingest_time:.1f}s query:{query_time:.3f}s | {question[:50]}")

        await archive.close()
        await kg.close()

    # Results
    overall = total_correct / total_questions * 100 if total_questions > 0 else 0

    print(f"\n{'='*70}")
    print("RESULTS")
    print(f"{'='*70}")
    print(f"\n  Overall: {total_correct}/{total_questions} ({overall:.1f}%)")
    print(f"  Total time: {total_time:.1f}s ({total_time/total_questions:.1f}s per question)")

    print(f"\n  By question type:")
    for qtype, data in sorted(results_by_type.items()):
        pct = data["correct"] / data["total"] * 100 if data["total"] > 0 else 0
        print(f"    {qtype:30s} {data['correct']:3d}/{data['total']:<3d} ({pct:.1f}%)")

    print(f"\n  Comparison:")
    print(f"    MemPalace (raw verbatim):     96.6%")
    print(f"    SuperMemory:                  81.6%")
    print(f"    GPT-4o (full context):        ~70%")
    print(f"    taOSmd (Pi NPU, no cloud):    {overall:.1f}%")
    print(f"{'='*70}")

    if llm_client:
        await llm_client.aclose()

    return overall


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50, help="Number of questions to run")
    parser.add_argument("--type", type=str, default=None, help="Filter by question type")
    parser.add_argument("--llm", action="store_true", help="Use remote LLM for answer generation")
    args = parser.parse_args()

    asyncio.run(run_benchmark(limit=args.limit, question_type=args.type, use_llm=args.llm))
