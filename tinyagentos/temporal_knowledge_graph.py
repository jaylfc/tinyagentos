"""Temporal Knowledge Graph for taOS.

Inspired by MemPalace's knowledge graph but adapted for taOS's agent-centric
architecture. Stores entity-relationship triples with temporal validity windows,
enabling point-in-time queries like "what was true about this project in January?"

Agents use this to maintain structured knowledge that changes over time, separate
from the raw memory store (UserMemoryStore) and ingested content (KnowledgeStore).
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS kg_entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'unknown',
    properties_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS kg_triples (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_id TEXT NOT NULL,
    valid_from REAL NOT NULL,
    valid_to REAL,
    confidence REAL NOT NULL DEFAULT 1.0,
    source TEXT NOT NULL DEFAULT '',
    source_ids TEXT NOT NULL DEFAULT '[]',
    superseded_by TEXT,
    appeared_count INTEGER NOT NULL DEFAULT 1,
    accessed_count INTEGER NOT NULL DEFAULT 0,
    last_accessed_at REAL,
    created_at REAL NOT NULL,
    FOREIGN KEY (subject_id) REFERENCES kg_entities(id),
    FOREIGN KEY (object_id) REFERENCES kg_entities(id)
);

CREATE INDEX IF NOT EXISTS idx_triples_subject ON kg_triples(subject_id);
CREATE INDEX IF NOT EXISTS idx_triples_object ON kg_triples(object_id);
CREATE INDEX IF NOT EXISTS idx_triples_predicate ON kg_triples(predicate);
CREATE INDEX IF NOT EXISTS idx_triples_valid ON kg_triples(valid_from, valid_to);
"""

# Memory type classification — regex-free, keyword-based for speed
MEMORY_TYPES = {
    "fact": ["is", "are", "has", "was", "uses", "runs", "supports"],
    "preference": ["prefer", "always", "like to", "rather", "favorite", "default to"],
    "decision": ["decided", "chose", "went with", "picked", "selected", "because"],
    "event": ["happened", "started", "finished", "launched", "released", "shipped"],
    "discovery": ["found", "discovered", "realized", "learned", "turns out", "figured out"],
}


def classify_memory_type(text: str) -> str:
    """Classify text into a memory type based on keyword matching."""
    text_lower = text.lower()
    scores: dict[str, int] = {t: 0 for t in MEMORY_TYPES}
    for mtype, keywords in MEMORY_TYPES.items():
        for kw in keywords:
            if kw in text_lower:
                scores[mtype] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "fact"


class TemporalKnowledgeGraph:
    """SQLite-backed temporal entity-relationship graph."""

    def __init__(self, db_path: str | Path = "data/knowledge-graph.db"):
        self._db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    async def init(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _entity_id(name: str) -> str:
        """Normalise entity name to a stable ID."""
        return name.lower().strip().replace(" ", "-").replace("'", "")

    @staticmethod
    def _triple_id(subject_id: str, predicate: str, object_id: str) -> str:
        raw = f"{subject_id}:{predicate}:{object_id}:{time.time()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------

    async def add_entity(
        self,
        name: str,
        entity_type: str = "unknown",
        properties: str = "{}",
    ) -> str:
        """Add or update an entity. Returns entity ID."""
        eid = self._entity_id(name)
        now = time.time()
        self._conn.execute(
            """INSERT INTO kg_entities (id, name, type, properties_json, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 name = excluded.name,
                 type = excluded.type,
                 properties_json = excluded.properties_json""",
            (eid, name, entity_type, properties, now),
        )
        self._conn.commit()
        return eid

    async def get_entity(self, name: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM kg_entities WHERE id = ?",
            (self._entity_id(name),),
        ).fetchone()
        return dict(row) if row else None

    async def list_entities(self, entity_type: str | None = None, limit: int = 100) -> list[dict]:
        if entity_type:
            rows = self._conn.execute(
                "SELECT * FROM kg_entities WHERE type = ? ORDER BY created_at DESC LIMIT ?",
                (entity_type, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM kg_entities ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Triples
    # ------------------------------------------------------------------

    async def add_triple(
        self,
        subject: str,
        predicate: str,
        obj: str,
        valid_from: float | None = None,
        confidence: float = 1.0,
        source: str = "",
        subject_type: str = "unknown",
        object_type: str = "unknown",
    ) -> str:
        """Add a relationship triple with temporal validity. Returns triple ID."""
        sub_id = await self.add_entity(subject, subject_type)
        obj_id = await self.add_entity(obj, object_type)
        now = time.time()
        vf = valid_from or now

        # Check for existing active triple with same subject/predicate/object
        existing = self._conn.execute(
            """SELECT id FROM kg_triples
               WHERE subject_id = ? AND predicate = ? AND object_id = ? AND valid_to IS NULL""",
            (sub_id, predicate, obj_id),
        ).fetchone()
        if existing:
            return existing["id"]

        tid = self._triple_id(sub_id, predicate, obj_id)
        self._conn.execute(
            """INSERT INTO kg_triples (id, subject_id, predicate, object_id, valid_from, valid_to, confidence, source, created_at)
               VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
            (tid, sub_id, predicate, obj_id, vf, confidence, source, now),
        )
        self._conn.commit()
        return tid

    async def invalidate(self, triple_id: str, ended_at: float | None = None) -> bool:
        """Mark a triple as no longer valid."""
        end = ended_at or time.time()
        cursor = self._conn.execute(
            "UPDATE kg_triples SET valid_to = ? WHERE id = ? AND valid_to IS NULL",
            (end, triple_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    async def update_fact(
        self,
        subject: str,
        predicate: str,
        old_object: str,
        new_object: str,
        source: str = "",
    ) -> str:
        """Update a fact by invalidating the old triple and creating a new one.
        E.g. update_fact("Jay", "works_on", "ProjectA", "ProjectB")
        """
        sub_id = self._entity_id(subject)
        old_obj_id = self._entity_id(old_object)
        # Invalidate old
        old_triple = self._conn.execute(
            """SELECT id FROM kg_triples
               WHERE subject_id = ? AND predicate = ? AND object_id = ? AND valid_to IS NULL""",
            (sub_id, predicate, old_obj_id),
        ).fetchone()
        if old_triple:
            await self.invalidate(old_triple["id"])
        # Create new
        return await self.add_triple(subject, predicate, new_object, source=source)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def query_entity(
        self,
        name: str,
        as_of: float | None = None,
        direction: str = "both",
        track_access: bool = True,
    ) -> list[dict]:
        """Get all relationships for an entity, optionally at a point in time.

        When track_access=True, increments accessed_count for retrieved triples
        (used for importance scoring: hit_rate = accessed / appeared).
        """
        eid = self._entity_id(name)
        ts = as_of or time.time()
        now = time.time()
        results = []

        if direction in ("both", "outgoing"):
            rows = self._conn.execute(
                """SELECT t.*, e.name as object_name, e.type as object_type
                   FROM kg_triples t
                   JOIN kg_entities e ON e.id = t.object_id
                   WHERE t.subject_id = ?
                     AND t.superseded_by IS NULL
                     AND t.valid_from <= ?
                     AND (t.valid_to IS NULL OR t.valid_to >= ?)""",
                (eid, ts, ts),
            ).fetchall()
            for r in rows:
                d = dict(r)
                d["direction"] = "outgoing"
                d["current"] = r["valid_to"] is None
                # Compute importance score
                appeared = d.get("appeared_count", 1) or 1
                accessed = d.get("accessed_count", 0)
                d["importance"] = round(accessed / appeared, 3) if appeared > 0 else 0
                results.append(d)
                # Track access
                if track_access:
                    self._conn.execute(
                        "UPDATE kg_triples SET accessed_count = accessed_count + 1, last_accessed_at = ? WHERE id = ?",
                        (now, r["id"]),
                    )

        if direction in ("both", "incoming"):
            rows = self._conn.execute(
                """SELECT t.*, e.name as subject_name, e.type as subject_type
                   FROM kg_triples t
                   JOIN kg_entities e ON e.id = t.subject_id
                   WHERE t.object_id = ?
                     AND t.superseded_by IS NULL
                     AND t.valid_from <= ?
                     AND (t.valid_to IS NULL OR t.valid_to >= ?)""",
                (eid, ts, ts),
            ).fetchall()
            for r in rows:
                d = dict(r)
                d["direction"] = "incoming"
                d["current"] = r["valid_to"] is None
                appeared = d.get("appeared_count", 1) or 1
                accessed = d.get("accessed_count", 0)
                d["importance"] = round(accessed / appeared, 3) if appeared > 0 else 0
                results.append(d)
                if track_access:
                    self._conn.execute(
                        "UPDATE kg_triples SET accessed_count = accessed_count + 1, last_accessed_at = ? WHERE id = ?",
                        (now, r["id"]),
                    )

        if track_access and results:
            self._conn.commit()

        return results

    async def query_predicate(self, predicate: str, as_of: float | None = None) -> list[dict]:
        """Get all triples with a given predicate, optionally at a point in time."""
        ts = as_of or time.time()
        rows = self._conn.execute(
            """SELECT t.*, s.name as subject_name, o.name as object_name
               FROM kg_triples t
               JOIN kg_entities s ON s.id = t.subject_id
               JOIN kg_entities o ON o.id = t.object_id
               WHERE t.predicate = ?
                 AND t.valid_from <= ?
                 AND (t.valid_to IS NULL OR t.valid_to >= ?)""",
            (predicate, ts, ts),
        ).fetchall()
        return [dict(r) for r in rows]

    async def timeline(self, name: str | None = None, limit: int = 50) -> list[dict]:
        """Chronological list of all facts, optionally filtered to one entity."""
        if name:
            eid = self._entity_id(name)
            rows = self._conn.execute(
                """SELECT t.*, s.name as subject_name, o.name as object_name
                   FROM kg_triples t
                   JOIN kg_entities s ON s.id = t.subject_id
                   JOIN kg_entities o ON o.id = t.object_id
                   WHERE t.subject_id = ? OR t.object_id = ?
                   ORDER BY t.valid_from DESC LIMIT ?""",
                (eid, eid, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT t.*, s.name as subject_name, o.name as object_name
                   FROM kg_triples t
                   JOIN kg_entities s ON s.id = t.subject_id
                   JOIN kg_entities o ON o.id = t.object_id
                   ORDER BY t.valid_from DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Contradiction detection
    # ------------------------------------------------------------------

    # Predicates where only one active value should exist per subject
    SINGULAR_PREDICATES = {
        "is_a", "works_on", "lives_in", "prefers", "uses_model",
        "runs_on", "managed_by", "owned_by", "located_in",
    }

    async def detect_contradictions(
        self,
        subject: str,
        predicate: str,
        new_object: str,
    ) -> list[dict]:
        """Check if adding this triple contradicts existing active facts.

        Returns list of conflicting triples. For singular predicates (where
        only one value makes sense), any existing active triple with the same
        subject+predicate but different object is a contradiction.
        """
        if predicate not in self.SINGULAR_PREDICATES:
            return []

        sub_id = self._entity_id(subject)
        new_obj_id = self._entity_id(new_object)

        rows = self._conn.execute(
            """SELECT t.*, o.name as object_name
               FROM kg_triples t
               JOIN kg_entities o ON o.id = t.object_id
               WHERE t.subject_id = ? AND t.predicate = ? AND t.valid_to IS NULL
                 AND t.object_id != ?""",
            (sub_id, predicate, new_obj_id),
        ).fetchall()

        return [dict(r) for r in rows]

    async def add_triple_with_contradiction_check(
        self,
        subject: str,
        predicate: str,
        obj: str,
        valid_from: float | None = None,
        confidence: float = 1.0,
        source: str = "",
        subject_type: str = "unknown",
        object_type: str = "unknown",
        auto_resolve: bool = True,
    ) -> dict:
        """Add a triple, checking for contradictions first.

        If auto_resolve is True and a contradiction is found for a singular
        predicate, the old triple is automatically invalidated and replaced.

        Returns {triple_id, contradictions_found, contradictions_resolved}.
        """
        contradictions = await self.detect_contradictions(subject, predicate, obj)

        if contradictions and auto_resolve:
            for c in contradictions:
                await self.invalidate(c["id"])

        tid = await self.add_triple(
            subject=subject, predicate=predicate, obj=obj,
            valid_from=valid_from, confidence=confidence, source=source,
            subject_type=subject_type, object_type=object_type,
        )

        return {
            "triple_id": tid,
            "contradictions_found": len(contradictions),
            "contradictions_resolved": len(contradictions) if auto_resolve else 0,
            "contradictions": [
                {"id": c["id"], "object": c["object_name"], "predicate": predicate}
                for c in contradictions
            ],
        }

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def stats(self) -> dict:
        """Get graph statistics."""
        entities = self._conn.execute("SELECT COUNT(*) as n FROM kg_entities").fetchone()["n"]
        triples = self._conn.execute("SELECT COUNT(*) as n FROM kg_triples").fetchone()["n"]
        active = self._conn.execute("SELECT COUNT(*) as n FROM kg_triples WHERE valid_to IS NULL").fetchone()["n"]
        return {"entities": entities, "triples": triples, "active_triples": active}
