"""Scheduler — dispatcher across registered Resources.

Phase 1 is deliberately simple: tasks are routed synchronously in the order
of their preferred_resources list, the first resource that passes admission
runs it, and we record everything to a bounded history for the Activity app.

No aging, no priority queue sharing across resources, no mid-task preemption,
no max_wait_ms enforcement — all Phase 2.
"""
from __future__ import annotations

import asyncio
import collections
import logging
import time
from typing import Optional

from tinyagentos.scheduler.resource import Resource
from tinyagentos.scheduler.types import (
    NoResourceAvailableError,
    Task,
    TaskRecord,
    TaskStatus,
)

logger = logging.getLogger(__name__)

HISTORY_MAX = 500


class Scheduler:
    """Registers Resources and dispatches Tasks.

    Thread/loop model: in-process with the main FastAPI app, asyncio-native.
    Task submission is async and returns when the task has actually run
    (or raised). This makes the caller's code read linearly:

        result = await scheduler.submit(task)
    """

    def __init__(self):
        self._resources: dict[str, Resource] = {}
        self._history: collections.deque[TaskRecord] = collections.deque(maxlen=HISTORY_MAX)
        self._lock = asyncio.Lock()
        self._submitted = 0
        self._rejected = 0
        self._errors = 0
        self._completed = 0

    def register(self, resource: Resource) -> None:
        """Add a resource. Safe to call during startup only."""
        if resource.name in self._resources:
            logger.warning("Re-registering resource %s", resource.name)
        self._resources[resource.name] = resource
        logger.info(
            "scheduler: registered resource %s (%s/%s/%s, concurrency=%d)",
            resource.name,
            resource.signature.platform,
            resource.signature.runtime,
            resource.signature.runtime_version or "any",
            resource.concurrency,
        )

    def resources(self) -> list[Resource]:
        return list(self._resources.values())

    def get_resource(self, name: str) -> Optional[Resource]:
        return self._resources.get(name)

    async def submit(self, task: Task) -> object:
        """Dispatch a task to the first admitted preferred resource.

        Raises :class:`NoResourceAvailableError` if no resource can run it.
        """
        self._submitted += 1
        record = TaskRecord(
            task_id=task.id,
            capability=task.capability.value,
            submitter=task.submitter,
            priority=int(task.priority),
            resource=None,
            status=TaskStatus.QUEUED,
            submitted_at=task.submitted_at,
        )
        self._history.append(record)

        tried: list[str] = []
        for ref in task.preferred_resources:
            resource = self._resources.get(ref.name)
            if resource is None:
                tried.append(f"{ref.name}=unknown")
                continue
            admitted, reason = resource.can_admit(task)
            if not admitted:
                tried.append(f"{ref.name}={reason}")
                continue

            # Found a home — run it
            record.resource = resource.name
            record.status = TaskStatus.RUNNING
            record.started_at = time.time()
            try:
                result, elapsed = await resource.run(task)
                record.status = TaskStatus.COMPLETE
                record.completed_at = time.time()
                record.elapsed_seconds = elapsed
                self._completed += 1
                return result
            except Exception as exc:  # noqa: BLE001 — propagate after recording
                record.status = TaskStatus.ERROR
                record.completed_at = time.time()
                record.error = str(exc)
                self._errors += 1
                logger.exception(
                    "scheduler: task %s on %s raised", task.id, resource.name
                )
                raise

        # No resource accepted
        record.status = TaskStatus.REJECTED
        record.completed_at = time.time()
        record.error = "; ".join(tried) or "no preferred resources"
        self._rejected += 1
        raise NoResourceAvailableError(
            f"no resource can run {task.capability.value} "
            f"(submitter={task.submitter}, tried: {record.error})"
        )

    def history(self, limit: int = 100) -> list[TaskRecord]:
        """Most recent task records, newest first."""
        return list(self._history)[-limit:][::-1]

    def stats(self) -> dict:
        active = sum(r.in_flight for r in self._resources.values())
        return {
            "submitted": self._submitted,
            "completed": self._completed,
            "errors": self._errors,
            "rejected": self._rejected,
            "active": active,
            "resources": [
                {
                    "name": r.name,
                    "platform": r.signature.platform,
                    "runtime": r.signature.runtime,
                    "runtime_version": r.signature.runtime_version,
                    "concurrency": r.concurrency,
                    "in_flight": r.in_flight,
                    "capabilities": sorted(r.capabilities),
                }
                for r in self._resources.values()
            ],
        }
