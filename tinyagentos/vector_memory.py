"""Lightweight vector memory store using QMD embeddings (taOSmd).

Stores text passages with their embeddings for semantic search.
Uses QMD's /embed endpoint for on-device NPU-accelerated embedding.
Vectors stored in SQLite for persistence — no external vector DB needed.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS vector_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    embedding TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vm_created ON vector_memory(created_at DESC);
"""


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorMemory:
    """SQLite-backed vector store with pluggable embeddings.

    Supports:
    - QMD NPU embeddings (Qwen3-Embed-0.6B on RK3588)
    - sentence-transformers CPU embeddings (all-MiniLM-L6-v2 — same as MemPalace)
    """

    def __init__(
        self,
        db_path: str | Path = "data/vector-memory.db",
        qmd_url: str = "http://localhost:7832",
        embed_mode: str = "qmd",  # "qmd" or "local"
        local_model: str = "all-MiniLM-L6-v2",
    ):
        self._db_path = str(db_path)
        self._qmd_url = qmd_url
        self._embed_mode = embed_mode
        self._local_model_name = local_model
        self._conn: sqlite3.Connection | None = None
        self._http = None
        self._local_model = None

    async def init(self, http_client=None) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._http = http_client

        # Load local embedding model if requested
        if self._embed_mode == "local":
            try:
                from sentence_transformers import SentenceTransformer
                self._local_model = SentenceTransformer(self._local_model_name)
                logger.info("Loaded local embedding model: %s", self._local_model_name)
            except ImportError:
                logger.warning("sentence-transformers not installed, falling back to QMD")
                self._embed_mode = "qmd"

    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    async def embed(self, text: str) -> list[float]:
        """Get embedding vector."""
        if self._embed_mode == "local" and self._local_model is not None:
            return self._embed_local(text)
        return await self._embed_qmd(text)

    def _embed_local(self, text: str) -> list[float]:
        """Embed using local sentence-transformers model (CPU)."""
        try:
            emb = self._local_model.encode(text[:512], convert_to_numpy=True)
            return emb.tolist()
        except Exception as e:
            logger.debug("Local embedding failed: %s", e)
            return []

    async def _embed_qmd(self, text: str) -> list[float]:
        """Embed using QMD NPU."""
        if not self._http:
            return []
        try:
            resp = await self._http.post(
                f"{self._qmd_url}/embed",
                json={"text": text[:512]},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json().get("embedding", [])
        except Exception as e:
            logger.debug("QMD embedding failed: %s", e)
        return []

    async def add(self, text: str, metadata: dict | None = None) -> int:
        """Add a text passage with its embedding. Returns row ID."""
        embedding = await self.embed(text)
        if not embedding:
            return -1

        now = time.time()
        cursor = self._conn.execute(
            "INSERT INTO vector_memory (text, embedding, metadata_json, created_at) VALUES (?, ?, ?, ?)",
            (text, json.dumps(embedding), json.dumps(metadata or {}), now),
        )
        self._conn.commit()
        return cursor.lastrowid

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        """Semantic search — find most similar passages to the query."""
        query_emb = await self.embed(query)
        if not query_emb:
            return []

        # Load all embeddings and compute similarity
        rows = self._conn.execute("SELECT * FROM vector_memory").fetchall()
        scored = []
        for row in rows:
            try:
                emb = json.loads(row["embedding"])
                sim = cosine_similarity(query_emb, emb)
                scored.append({
                    "id": row["id"],
                    "text": row["text"],
                    "similarity": round(sim, 4),
                    "metadata": json.loads(row["metadata_json"]),
                    "created_at": row["created_at"],
                })
            except (json.JSONDecodeError, TypeError):
                continue

        # Sort by similarity descending
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:limit]

    async def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) as n FROM vector_memory").fetchone()
        return row["n"]

    async def clear(self) -> int:
        cursor = self._conn.execute("DELETE FROM vector_memory")
        self._conn.commit()
        return cursor.rowcount
