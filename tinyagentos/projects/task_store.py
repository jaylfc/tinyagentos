from __future__ import annotations

import json
import time

from tinyagentos.base_store import BaseStore
from tinyagentos.projects.ids import new_id

TASK_SCHEMA = """
CREATE TABLE IF NOT EXISTS project_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    parent_task_id TEXT,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    priority INTEGER NOT NULL DEFAULT 0,
    labels TEXT NOT NULL DEFAULT '[]',
    assignee_id TEXT,
    claimed_by TEXT,
    claimed_at REAL,
    closed_at REAL,
    closed_by TEXT,
    close_reason TEXT,
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON project_tasks(project_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON project_tasks(parent_task_id);

CREATE TABLE IF NOT EXISTS task_relationships (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    from_task_id TEXT NOT NULL,
    to_task_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE (from_task_id, to_task_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_rel_from ON task_relationships(from_task_id);
CREATE INDEX IF NOT EXISTS idx_rel_to ON task_relationships(to_task_id);

CREATE TABLE IF NOT EXISTS task_comments (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    replies_to_comment_id TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comments_task ON task_comments(task_id, created_at);

CREATE VIEW IF NOT EXISTS ready_tasks AS
SELECT t.*
FROM project_tasks t
WHERE t.status = 'open'
  AND t.claimed_by IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM task_relationships r
      JOIN project_tasks bt ON bt.id = r.to_task_id
      WHERE r.from_task_id = t.id
        AND r.kind = 'blocks'
        AND bt.status NOT IN ('closed', 'cancelled')
  );
"""

_TASK_JSON_FIELDS = ("labels",)


def _row_to_task(row, description) -> dict:
    keys = [d[0] for d in description]
    t = dict(zip(keys, row))
    for f in _TASK_JSON_FIELDS:
        if f in t and t[f] is not None:
            t[f] = json.loads(t[f])
    return t


class ProjectTaskStore(BaseStore):
    SCHEMA = TASK_SCHEMA

    async def create_task(
        self,
        project_id: str,
        title: str,
        created_by: str,
        body: str = "",
        priority: int = 0,
        labels: list[str] | None = None,
        assignee_id: str | None = None,
        parent_task_id: str | None = None,
    ) -> dict:
        tid = new_id("tsk")
        now = time.time()
        await self._db.execute(
            """INSERT INTO project_tasks
               (id, project_id, parent_task_id, title, body, status, priority, labels,
                assignee_id, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?)""",
            (
                tid, project_id, parent_task_id, title, body, priority,
                json.dumps(labels or []), assignee_id, created_by, now, now,
            ),
        )
        await self._db.commit()
        return await self.get_task(tid)

    async def get_task(self, task_id: str) -> dict | None:
        async with self._db.execute(
            "SELECT * FROM project_tasks WHERE id = ?", (task_id,)
        ) as cur:
            row = await cur.fetchone()
            if row is None:
                return None
            return _row_to_task(row, cur.description)
