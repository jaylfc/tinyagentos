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

    async def list_tasks(
        self,
        project_id: str,
        status: str | None = None,
        parent_task_id: str | None = None,
    ) -> list[dict]:
        conds = ["project_id = ?"]
        params: list = [project_id]
        if status is not None:
            conds.append("status = ?")
            params.append(status)
        if parent_task_id is not None:
            conds.append("parent_task_id = ?")
            params.append(parent_task_id)
        sql = f"SELECT * FROM project_tasks WHERE {' AND '.join(conds)} ORDER BY created_at ASC"
        async with self._db.execute(sql, params) as cur:
            rows = await cur.fetchall()
            desc = cur.description
        return [_row_to_task(r, desc) for r in rows]

    async def update_task(
        self,
        task_id: str,
        title: str | None = None,
        body: str | None = None,
        priority: int | None = None,
        labels: list[str] | None = None,
        assignee_id: str | None = None,
    ) -> None:
        sets: list[str] = []
        params: list = []
        if title is not None:
            sets.append("title = ?"); params.append(title)
        if body is not None:
            sets.append("body = ?"); params.append(body)
        if priority is not None:
            sets.append("priority = ?"); params.append(priority)
        if labels is not None:
            sets.append("labels = ?"); params.append(json.dumps(labels))
        if assignee_id is not None:
            sets.append("assignee_id = ?"); params.append(assignee_id)
        if not sets:
            return
        sets.append("updated_at = ?"); params.append(time.time())
        params.append(task_id)
        await self._db.execute(
            f"UPDATE project_tasks SET {', '.join(sets)} WHERE id = ?", params
        )
        await self._db.commit()

    async def claim_task(self, task_id: str, claimer_id: str) -> bool:
        now = time.time()
        cursor = await self._db.execute(
            """UPDATE project_tasks
               SET claimed_by = ?, claimed_at = ?, status = 'claimed', updated_at = ?
               WHERE id = ? AND claimed_by IS NULL AND status = 'open'""",
            (claimer_id, now, now, task_id),
        )
        await self._db.commit()
        return cursor.rowcount == 1

    async def release_task(self, task_id: str, releaser_id: str) -> bool:
        now = time.time()
        cursor = await self._db.execute(
            """UPDATE project_tasks
               SET claimed_by = NULL, claimed_at = NULL, status = 'open', updated_at = ?
               WHERE id = ? AND claimed_by = ?""",
            (now, task_id, releaser_id),
        )
        await self._db.commit()
        return cursor.rowcount == 1

    async def close_task(
        self,
        task_id: str,
        closed_by: str,
        reason: str | None = None,
    ) -> bool:
        now = time.time()
        cursor = await self._db.execute(
            """UPDATE project_tasks
               SET status = 'closed', closed_by = ?, closed_at = ?, close_reason = ?, updated_at = ?
               WHERE id = ? AND status NOT IN ('closed', 'cancelled')""",
            (closed_by, now, reason, now, task_id),
        )
        await self._db.commit()
        return cursor.rowcount == 1
