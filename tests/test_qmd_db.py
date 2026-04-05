import sqlite3
import pytest
from tinyagentos.qmd_db import QmdDatabase

def create_test_qmd_db(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE content (hash TEXT PRIMARY KEY, doc TEXT NOT NULL, created_at TEXT NOT NULL)")
    conn.execute("""
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection TEXT NOT NULL, path TEXT NOT NULL, title TEXT NOT NULL,
            hash TEXT NOT NULL, created_at TEXT NOT NULL, modified_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(collection, path)
        )
    """)
    conn.execute("CREATE TABLE content_vectors (hash TEXT NOT NULL, seq INTEGER NOT NULL DEFAULT 0, pos INTEGER NOT NULL DEFAULT 0, model TEXT NOT NULL, embedded_at TEXT NOT NULL, PRIMARY KEY (hash, seq))")
    conn.execute("CREATE TABLE store_collections (name TEXT PRIMARY KEY, path TEXT NOT NULL, pattern TEXT NOT NULL DEFAULT '**/*.md')")
    conn.execute("CREATE VIRTUAL TABLE documents_fts USING fts5(filepath, title, body, tokenize='porter unicode61')")

    conn.execute("INSERT INTO content VALUES ('abc123', 'Meeting notes about Q2 roadmap and budget planning', '2026-04-01')")
    conn.execute("INSERT INTO content VALUES ('def456', 'Python tutorial on async programming with asyncio', '2026-04-02')")
    conn.execute("INSERT INTO content VALUES ('ghi789', 'Weekly standup: discussed deployment pipeline issues', '2026-04-03')")
    conn.execute("INSERT INTO documents VALUES (1, 'transcripts', 'meeting-q2.md', 'Q2 Roadmap Meeting', 'abc123', '2026-04-01', '2026-04-01', 1)")
    conn.execute("INSERT INTO documents VALUES (2, 'notes', 'async-python.md', 'Async Python', 'def456', '2026-04-02', '2026-04-02', 1)")
    conn.execute("INSERT INTO documents VALUES (3, 'transcripts', 'standup-apr3.md', 'Weekly Standup', 'ghi789', '2026-04-03', '2026-04-03', 1)")
    conn.execute("INSERT INTO content_vectors VALUES ('abc123', 0, 0, 'qwen3-embedding', '2026-04-01')")
    conn.execute("INSERT INTO content_vectors VALUES ('def456', 0, 0, 'qwen3-embedding', '2026-04-02')")
    conn.execute("INSERT INTO content_vectors VALUES ('ghi789', 0, 0, 'qwen3-embedding', '2026-04-03')")
    conn.execute("INSERT INTO store_collections VALUES ('transcripts', '/data/transcripts', '**/*.md')")
    conn.execute("INSERT INTO store_collections VALUES ('notes', '/data/notes', '**/*.md')")
    conn.execute("INSERT INTO documents_fts (rowid, filepath, title, body) VALUES (1, 'transcripts/meeting-q2.md', 'Q2 Roadmap Meeting', 'Meeting notes about Q2 roadmap and budget planning')")
    conn.execute("INSERT INTO documents_fts (rowid, filepath, title, body) VALUES (2, 'notes/async-python.md', 'Async Python', 'Python tutorial on async programming with asyncio')")
    conn.execute("INSERT INTO documents_fts (rowid, filepath, title, body) VALUES (3, 'transcripts/standup-apr3.md', 'Weekly Standup', 'Weekly standup: discussed deployment pipeline issues')")
    conn.commit()
    conn.close()

@pytest.fixture
def qmd_db_path(tmp_path):
    db_path = tmp_path / "index.sqlite"
    create_test_qmd_db(db_path)
    return db_path

class TestQmdDatabase:
    def test_collections(self, qmd_db_path):
        db = QmdDatabase(qmd_db_path)
        collections = db.collections()
        assert len(collections) == 2
        names = {c["name"] for c in collections}
        assert "transcripts" in names
        assert "notes" in names

    def test_vector_count(self, qmd_db_path):
        db = QmdDatabase(qmd_db_path)
        assert db.vector_count() == 3

    def test_vector_count_by_collection(self, qmd_db_path):
        db = QmdDatabase(qmd_db_path)
        assert db.vector_count(collection="transcripts") == 2
        assert db.vector_count(collection="notes") == 1

    def test_browse_all(self, qmd_db_path):
        db = QmdDatabase(qmd_db_path)
        results = db.browse(limit=10, offset=0)
        assert len(results) == 3
        assert results[0]["hash"] == "ghi789"

    def test_browse_by_collection(self, qmd_db_path):
        db = QmdDatabase(qmd_db_path)
        results = db.browse(collection="transcripts", limit=10, offset=0)
        assert len(results) == 2
        assert all(r["collection"] == "transcripts" for r in results)

    def test_keyword_search(self, qmd_db_path):
        db = QmdDatabase(qmd_db_path)
        results = db.keyword_search("roadmap", limit=10)
        assert len(results) >= 1
        assert results[0]["hash"] == "abc123"

    def test_keyword_search_no_results(self, qmd_db_path):
        db = QmdDatabase(qmd_db_path)
        results = db.keyword_search("xyznonexistent", limit=10)
        assert results == []

    def test_delete_chunk(self, qmd_db_path):
        db = QmdDatabase(qmd_db_path)
        assert db.vector_count() == 3
        db.delete_chunk("abc123")
        assert db.vector_count() == 2
        results = db.keyword_search("roadmap", limit=10)
        assert len(results) == 0

    def test_last_embedded_at(self, qmd_db_path):
        db = QmdDatabase(qmd_db_path)
        ts = db.last_embedded_at()
        assert ts == "2026-04-03"
