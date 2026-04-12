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
        embed_mode: str = "qmd",  # "qmd", "local", or "onnx"
        local_model: str = "all-MiniLM-L6-v2",
        onnx_path: str = "",
    ):
        self._db_path = str(db_path)
        self._qmd_url = qmd_url
        self._embed_mode = embed_mode
        self._local_model_name = local_model
        self._onnx_path = onnx_path
        self._conn: sqlite3.Connection | None = None
        self._http = None
        self._local_model = None
        self._onnx_session = None
        self._onnx_tokenizer = None

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
        elif self._embed_mode == "onnx":
            try:
                import onnxruntime as ort
                from transformers import AutoTokenizer
                model_dir = self._onnx_path or "models/minilm-onnx"
                self._onnx_session = ort.InferenceSession(
                    f"{model_dir}/model.onnx",
                    providers=["CPUExecutionProvider"],
                )
                self._onnx_tokenizer = AutoTokenizer.from_pretrained(model_dir)
                logger.info("Loaded ONNX embedding model from %s", model_dir)
            except Exception as e:
                logger.warning("ONNX model failed to load: %s, falling back to QMD", e)
                self._embed_mode = "qmd"

    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    async def embed(self, text: str) -> list[float]:
        """Get embedding vector."""
        if self._embed_mode == "onnx" and self._onnx_session is not None:
            return self._embed_onnx(text)
        if self._embed_mode == "local" and self._local_model is not None:
            return self._embed_local(text)
        return await self._embed_qmd(text)

    def _embed_onnx(self, text: str) -> list[float]:
        """Embed using ONNX Runtime (fast CPU inference, no PyTorch)."""
        import numpy as np
        try:
            inputs = self._onnx_tokenizer(text[:512], return_tensors="np", padding=True, truncation=True)
            feed = {
                "input_ids": inputs["input_ids"].astype(np.int64),
                "attention_mask": inputs["attention_mask"].astype(np.int64),
            }
            # Add token_type_ids if the model expects it
            if any(inp.name == "token_type_ids" for inp in self._onnx_session.get_inputs()):
                feed["token_type_ids"] = np.zeros_like(inputs["input_ids"], dtype=np.int64)

            outputs = self._onnx_session.run(None, feed)

            # Check if model provides sentence_embedding directly
            output_names = [o.name for o in self._onnx_session.get_outputs()]
            if "sentence_embedding" in output_names:
                idx = output_names.index("sentence_embedding")
                emb = outputs[idx][0]  # (384,)
            else:
                # Manual mean pooling
                token_embeddings = outputs[0]
                mask = inputs["attention_mask"][..., np.newaxis].astype(np.float32)
                pooled = (token_embeddings * mask).sum(axis=1) / mask.sum(axis=1)
                emb = pooled[0]

            # Normalize
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb = emb / norm
            return emb.tolist()
        except Exception as e:
            logger.debug("ONNX embedding failed: %s", e)
            return []

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

    async def search(self, query: str, limit: int = 5, hybrid: bool = True) -> list[dict]:
        """Semantic search with optional hybrid keyword boosting.

        When hybrid=True, boosts results that contain exact keywords from
        the query (similar to MemPalace's hybrid scoring approach).
        """
        query_emb = await self.embed(query)
        if not query_emb:
            return []

        # Extract meaningful keywords from query (3+ chars, not stop words)
        stop = {"the", "what", "how", "did", "does", "was", "were", "are", "is",
                "my", "your", "for", "and", "but", "not", "with", "this", "that",
                "from", "have", "has", "had", "been", "can", "will", "would",
                "when", "where", "which", "who", "whom", "many", "much", "long"}
        keywords = [w.lower().strip("?.,!") for w in query.split() if len(w) > 2 and w.lower() not in stop]

        # Load all embeddings and compute similarity using numpy batch operations
        rows = self._conn.execute("SELECT id, text, embedding, metadata_json, created_at FROM vector_memory").fetchall()
        if not rows:
            return []

        try:
            import numpy as np

            # Parse all embeddings into a matrix
            ids = []
            texts = []
            metas = []
            created = []
            emb_list = []
            for row in rows:
                try:
                    emb = json.loads(row["embedding"])
                    if emb:
                        ids.append(row["id"])
                        texts.append(row["text"])
                        metas.append(row["metadata_json"])
                        created.append(row["created_at"])
                        emb_list.append(emb)
                except (json.JSONDecodeError, TypeError):
                    continue

            if not emb_list:
                return []

            # Batch cosine similarity with numpy
            query_vec = np.array(query_emb, dtype=np.float32)
            emb_matrix = np.array(emb_list, dtype=np.float32)
            # Normalise
            query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)
            emb_norms = emb_matrix / (np.linalg.norm(emb_matrix, axis=1, keepdims=True) + 1e-8)
            # Dot product = cosine similarity (both normalised)
            similarities = emb_norms @ query_norm

            # Hybrid keyword boost
            if hybrid and keywords:
                for i, text in enumerate(texts):
                    text_lower = text.lower()
                    keyword_hits = sum(1 for kw in keywords if kw in text_lower)
                    boost = keyword_hits / len(keywords) * 0.3
                    similarities[i] = min(1.0, similarities[i] + boost)

            # Get top-k indices
            top_indices = np.argsort(similarities)[::-1][:limit]

            return [
                {
                    "id": ids[i],
                    "text": texts[i],
                    "similarity": round(float(similarities[i]), 4),
                    "metadata": json.loads(metas[i]),
                    "created_at": created[i],
                }
                for i in top_indices
            ]
        except ImportError:
            # Fallback to Python loop if numpy not available
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
            scored.sort(key=lambda x: x["similarity"], reverse=True)
            return scored[:limit]

    async def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) as n FROM vector_memory").fetchone()
        return row["n"]

    async def clear(self) -> int:
        cursor = self._conn.execute("DELETE FROM vector_memory")
        self._conn.commit()
        return cursor.rowcount
