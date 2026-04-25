from __future__ import annotations

import json
import time

from tinyagentos.base_store import BaseStore
from tinyagentos.projects.ids import new_id

PROJECTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    archived_at REAL,
    deleted_at REAL,
    settings TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);

CREATE TABLE IF NOT EXISTS project_members (
    project_id TEXT NOT NULL,
    member_id TEXT NOT NULL,
    member_kind TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    source_agent_id TEXT,
    memory_seed TEXT NOT NULL DEFAULT 'none',
    added_at REAL NOT NULL,
    PRIMARY KEY (project_id, member_id)
);
CREATE INDEX IF NOT EXISTS idx_project_members_member ON project_members(member_id);

CREATE TABLE IF NOT EXISTS project_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_project_activity_project ON project_activity(project_id, created_at DESC);
"""

_JSON_FIELDS = ("settings",)


def _row_to_project(row, description) -> dict:
    keys = [d[0] for d in description]
    p = dict(zip(keys, row))
    for f in _JSON_FIELDS:
        if f in p and p[f] is not None:
            p[f] = json.loads(p[f])
    return p


class ProjectStore(BaseStore):
    SCHEMA = PROJECTS_SCHEMA

    async def create_project(
        self,
        name: str,
        slug: str,
        created_by: str,
        description: str = "",
        settings: dict | None = None,
    ) -> dict:
        existing = await self.get_project_by_slug(slug)
        if existing is not None:
            raise ValueError(f"slug already used: {slug}")
        pid = new_id("prj")
        now = time.time()
        await self._db.execute(
            """INSERT INTO projects
               (id, name, slug, description, status, created_by, created_at, updated_at, settings)
               VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?)""",
            (pid, name, slug, description, created_by, now, now, json.dumps(settings or {})),
        )
        await self._db.commit()
        return await self.get_project(pid)

    async def get_project(self, project_id: str) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ) as cur:
            row = await cur.fetchone()
            if row is None:
                return None
            return _row_to_project(row, cur.description)

    async def get_project_by_slug(self, slug: str) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM projects WHERE slug = ?", (slug,)
        ) as cur:
            row = await cur.fetchone()
            if row is None:
                return None
            return _row_to_project(row, cur.description)
