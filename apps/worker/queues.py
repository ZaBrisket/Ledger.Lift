"""RQ queue helpers providing retry, DLQ, and metrics instrumentation."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from rq import Queue
from rq.retry import Retry
from rq.job import Job

from apps.worker.config import get_worker_settings
from apps.worker.infra.redis import get_redis_connection
from apps.worker import metrics


class RetryableJobError(Exception):
    """Exception type indicating a job may be retried."""


class FatalJobError(Exception):
    """Exception type indicating the job should not be retried."""


@dataclass
class JobEnvelope:
    """Metadata envelope included with every queued job."""

    job_id: Optional[str]
    priority: str
    user_id: Optional[str]
    p95_hint_ms: Optional[int]
    content_hashes: Iterable[str]
    payload: Dict[str, Any]

    def serialize(self) -> Dict[str, Any]:
        settings = get_worker_settings()
        return {
            "version": settings.work_version,
            "schema_version": settings.schema_version,
            "job_id": self.job_id,
            "priority": self.priority,
            "user_id": self.user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "p95_hint_ms": self.p95_hint_ms,
            "content_hashes": list(self.content_hashes),
            "payload": self.payload,
        }


def _queues() -> Dict[str, Queue]:
    settings = get_worker_settings()
    connection = get_redis_connection()
    return {
        "high": Queue(settings.rq_high_queue, connection=connection),
        "default": Queue(settings.rq_default_queue, connection=connection),
        "low": Queue(settings.rq_low_queue, connection=connection),
        "dead": Queue(settings.rq_dead_queue, connection=connection),
    }


def get_queue(priority: str) -> Queue:
    try:
        queue = _queues()[priority]
    except KeyError as exc:  # pragma: no cover - developer error
        raise ValueError(f"Unknown queue priority: {priority}") from exc
    return queue


def _exponential_backoff(max_retries: int, base: int = 15, jitter: float = 0.25) -> Iterable[int]:
    intervals: list[int] = []
    for attempt in range(max_retries):
        base_interval = base * (2 ** attempt)
        jitter_window = max(1, int(base_interval * jitter))
        intervals.append(base_interval + random.randint(0, jitter_window))
    return intervals


def enqueue_with_retry(
    func: str,
    *,
    args: Optional[Iterable[Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    priority: str = "default",
    envelope: Optional[JobEnvelope] = None,
    description: Optional[str] = None,
    max_retries: Optional[int] = None,
    ttl: Optional[int] = None,
) -> Job:
    """Enqueue a job with exponential backoff and DLQ routing."""

    settings = get_worker_settings()
    queue = get_queue(priority)
    args = tuple(args or ())
    kwargs = dict(kwargs or {})
    max_retries = max_retries if max_retries is not None else settings.redis_max_retries

    retry = Retry(max=max_retries, interval=list(_exponential_backoff(max_retries)))
    job = queue.enqueue(
        func,
        args=args,
        kwargs=kwargs,
        job_id=envelope.job_id if envelope else None,
        description=description,
        retry=retry,
        result_ttl=ttl,
    )

    serialized = envelope.serialize() if envelope else {}
    serialized.update(
        {
            "max_retries": max_retries,
            "dlq_queue": get_queue("dead").name,
            "enqueued_at": time.time(),
            "priority": priority,
        }
    )
    job.meta.update(serialized)
    job.save_meta()

    metrics.observe_enqueue(queue.name)
    metrics.update_depth(queue.name, queue.count)

    return job


def route_to_dlq(job: Job, *, reason: str) -> Job:
    """Move failed jobs to the DLQ for later inspection."""

    dead_queue = get_queue("dead")
    payload = job.meta.copy()
    payload.update({"failed_reason": reason})
    new_job = dead_queue.enqueue(
        "apps.worker.worker.rq_jobs.dead_letter_handler",
        kwargs={"payload": payload},
        description=f"DLQ for {job.id}",
    )
    new_job.meta.update(payload)
    new_job.save_meta()
    metrics.observe_dlq(dead_queue.name)
    metrics.update_depth(dead_queue.name, dead_queue.count)
    return new_job


__all__ = [
    "RetryableJobError",
    "FatalJobError",
    "JobEnvelope",
    "enqueue_with_retry",
    "get_queue",
    "route_to_dlq",
]
