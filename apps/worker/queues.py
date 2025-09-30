"""RQ queue helpers for Ledger Lift worker."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

try:
    from rq import Queue
    from rq.job import Job
    from rq.retry import Retry
    from rq.registry import (
        DeferredJobRegistry,
        FailedJobRegistry,
        FinishedJobRegistry,
        ScheduledJobRegistry,
        StartedJobRegistry,
    )
except ImportError:  # pragma: no cover
    class Retry:  # type: ignore
        def __init__(self, max: int, interval):
            self.max = max
            self.interval = interval

    class Job:  # type: ignore
        def __init__(self, *, job_id: str, origin: str, connection=None, meta=None, args=(), kwargs=None):
            self.id = job_id
            self.origin = origin
            self.connection = connection
            self.meta = meta or {}
            self.args = args
            self.kwargs = kwargs or {}
            self.retries_left = 0

        def save_meta(self):
            return None

    class _StubRegistry:  # type: ignore
        def __init__(self, queue: str, connection=None):
            self.queue = queue
            self.connection = connection

        def count(self) -> int:
            return 0

    class StartedJobRegistry(_StubRegistry):
        ...

    class FinishedJobRegistry(_StubRegistry):
        ...

    class FailedJobRegistry(_StubRegistry):
        ...

    class DeferredJobRegistry(_StubRegistry):
        ...

    class ScheduledJobRegistry(_StubRegistry):
        ...

    class Queue:  # type: ignore
        def __init__(self, name: str, connection=None, default_timeout=None):
            self.name = name
            self.connection = connection
            self.default_timeout = default_timeout
            self._jobs: list[Job] = []

        def enqueue(
            self,
            func,
            args=(),
            kwargs=None,
            job_id: str | None = None,
            retry=None,
            failure_callback=None,
            meta=None,
            description=None,
            result_ttl=None,
        ):
            job = Job(
                job_id=job_id or "stub-job",
                origin=self.name,
                connection=self.connection,
                meta=meta,
                args=args,
                kwargs=kwargs,
            )
            self._jobs.append(job)
            return job
            
        def count(self) -> int:
            return len(self._jobs)

from apps.worker.config import settings
from apps.worker.infra.redis import get_redis_connection, is_emergency_stopped
from apps.worker.metrics import (
    record_dead_letter,
    record_enqueue,
    record_retry_scheduled,
    update_queue_depth,
    update_workers_busy,
)


@dataclass(frozen=True)
class QueueNames:
    """Encapsulates queue name mapping."""

    high: str = settings.rq_high_queue
    default: str = settings.rq_default_queue
    low: str = settings.rq_low_queue
    dead: str = settings.rq_dlq


def get_queue(priority: str, *, connection=None, job_timeout: Optional[int] = None) -> Queue:
    """Return the queue for the requested priority."""

    queues = QueueNames()
    priority = priority.lower()
    match priority:
        case "high":
            name = queues.high
        case "low":
            name = queues.low
        case _:
            name = queues.default
    connection = connection or get_redis_connection()
    return Queue(name, connection=connection, default_timeout=job_timeout)


@dataclass(frozen=True)
class JobRegistries:
    """Holds handles to relevant RQ job registries for a queue."""

    started: StartedJobRegistry
    finished: FinishedJobRegistry
    failed: FailedJobRegistry
    deferred: DeferredJobRegistry
    scheduled: ScheduledJobRegistry


def get_job_registries(queue_name: str, *, connection=None) -> JobRegistries:
    """Return registries for the provided queue name."""

    conn = connection or get_redis_connection()
    return JobRegistries(
        started=StartedJobRegistry(queue_name, connection=conn),
        finished=FinishedJobRegistry(queue_name, connection=conn),
        failed=FailedJobRegistry(queue_name, connection=conn),
        deferred=DeferredJobRegistry(queue_name, connection=conn),
        scheduled=ScheduledJobRegistry(queue_name, connection=conn),
    )


def _safe_metric_value(value) -> int:
    if callable(value):
        try:
            return int(value())
        except Exception:  # pragma: no cover - defensive programming
            return 0
    try:
        return int(value)
    except Exception:  # pragma: no cover - defensive programming
        return 0


def record_queue_state(queue: Queue) -> None:
    """Update gauges for queue depth and workers busy."""

    depth_getter = getattr(queue, "count", None)
    depth = _safe_metric_value(depth_getter) if depth_getter is not None else 0
    update_queue_depth(queue.name, depth)

    registries = get_job_registries(queue.name, connection=queue.connection)
    busy = _safe_metric_value(getattr(registries.started, "count", None))
    update_workers_busy(queue.name, busy)


def compute_backoff_intervals(
    max_retries: int,
    *,
    base_seconds: int = 10,
    jitter_ratio: float = 0.25,
    rng: Optional[random.Random] = None,
) -> Sequence[int]:
    """Return retry delays using exponential backoff with jitter."""

    rng = rng or random.Random()
    intervals: list[int] = []
    for attempt in range(max_retries):
        base = base_seconds * (2**attempt)
        jitter = rng.uniform(0, base * jitter_ratio)
        intervals.append(int(base + jitter))
    return intervals


def _serialize_dead_letter(job: Job, exc_type: Optional[type], exc_value: Optional[BaseException]) -> str:
    payload = {
        "job_id": job.id,
        "queue": job.origin,
        "args": job.args,
        "kwargs": job.kwargs,
        "meta": job.meta,
        "exc_type": exc_type.__name__ if exc_type else None,
        "exc_message": str(exc_value) if exc_value else None,
    }
    return json.dumps(payload, default=str)


def _dead_letter_callback(job: Job, exc_type: Optional[type], exc_value: Optional[BaseException], _traceback: Any):
    """Route the job to a dead letter sink once retries are exhausted."""

    # RQ stores retries_left attribute when using Retry helper.
    if getattr(job, "retries_left", 0) > 0:
        # Another retry will be scheduled automatically.
        record_retry_scheduled(job.origin or settings.rq_default_queue)
        return

    if is_emergency_stopped(job.connection):
        # If emergency stop triggered mid-flight, we still mark as DLQ for visibility.
        record_retry_scheduled(job.origin or settings.rq_default_queue)

    serialized = _serialize_dead_letter(job, exc_type, exc_value)
    job.connection.hset(f"deadletter:{settings.rq_dlq}", job.id, serialized)
    job.meta["dead_letter"] = True
    job.save_meta()
    record_dead_letter(job.origin or settings.rq_default_queue)
    try:
        record_queue_state(Queue(job.origin, connection=job.connection))
    except Exception:  # pragma: no cover - defensive safety when queue can't be instantiated
        pass


def enqueue_with_retry(
    func: Any,
    *,
    args: Optional[Iterable[Any]] = None,
    kwargs: Optional[dict[str, Any]] = None,
    priority: str = "default",
    job_id: Optional[str] = None,
    description: Optional[str] = None,
    max_retries: Optional[int] = None,
    connection=None,
    metadata: Optional[dict[str, Any]] = None,
    job_timeout: Optional[int] = None,
) -> Job:
    """Enqueue a job with retry/backoff and DLQ routing."""

    args = list(args or [])
    kwargs = dict(kwargs or {})
    connection = connection or get_redis_connection()

    if is_emergency_stopped(connection):
        raise RuntimeError("Emergency stop is active; refusing to enqueue work.")

    queue = get_queue(priority, connection=connection, job_timeout=job_timeout)

    retry_count = settings.redis_max_retries if max_retries is None else max_retries
    intervals = compute_backoff_intervals(retry_count)
    retry = Retry(max=retry_count, interval=intervals)

    meta = {
        "version": metadata.get("version") if metadata else 1,
        "schema_version": metadata.get("schema_version") if metadata else 1,
    }
    if metadata:
        meta.update(metadata)

    job = queue.enqueue(
        func,
        args=tuple(args),
        kwargs=kwargs,
        job_id=job_id,
        retry=retry,
        failure_callback=_dead_letter_callback,
        meta=meta,
        description=description,
        result_ttl=0,
    )
    record_enqueue(queue.name, priority)
    record_queue_state(queue)
    return job
