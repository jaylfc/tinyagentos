"""TinyAgentOS resource scheduler.

Central arbiter for inference work across NPU, GPU, CPU, and cluster workers.

Callers submit Tasks with a capability + priority + preferred-resource list;
the scheduler picks the first admitted resource and runs it. Availability is
driven by live backend probes (BackendCatalog), not filesystem state.

See docs/design/resource-scheduler.md for the full design.
"""
from tinyagentos.scheduler.types import (
    Capability,
    NoResourceAvailableError,
    Priority,
    ResourceRef,
    ResourceSignature,
    Task,
    TaskRecord,
    TaskStatus,
)
from tinyagentos.scheduler.backend_catalog import BackendCatalog, BackendEntry
from tinyagentos.scheduler.resource import Resource
from tinyagentos.scheduler.scheduler import Scheduler
from tinyagentos.scheduler.score_cache import ScoreCache
from tinyagentos.scheduler.task_scheduler import TaskScheduler

__all__ = [
    "BackendCatalog",
    "BackendEntry",
    "Capability",
    "NoResourceAvailableError",
    "Priority",
    "Resource",
    "ResourceRef",
    "ResourceSignature",
    "Scheduler",
    "ScoreCache",
    "Task",
    "TaskRecord",
    "TaskScheduler",
    "TaskStatus",
]
