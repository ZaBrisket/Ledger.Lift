"""Prometheus metrics helpers for worker service."""
from __future__ import annotations

from typing import Optional

from prometheus_client import Counter, Gauge, Histogram

# Queue metrics
QUEUE_ENQUEUED = Counter(
    "ledger_lift_worker_jobs_enqueued_total",
    "Number of jobs enqueued by priority",
    ["queue", "priority"],
)

RETRY_SCHEDULED = Counter(
    "ledger_lift_worker_job_retries_scheduled_total",
    "Retries scheduled by queue",
    ["queue"],
)

DEAD_LETTER_TOTAL = Counter(
    "ledger_lift_worker_dead_letter_total",
    "Jobs routed to the dead letter queue",
    ["queue"],
)

JOB_DURATION_SECONDS = Histogram(
    "ledger_lift_job_duration_seconds",
    "Observed job execution durations",
    ["queue", "result"],
)

QUEUE_DEPTH = Gauge(
    "ledger_lift_queue_depth",
    "Number of jobs waiting in the queue",
    ["queue"],
)

WORKERS_BUSY = Gauge(
    "ledger_lift_workers_busy",
    "Number of workers busy per queue",
    ["queue"],
)


def record_enqueue(queue_name: str, priority: str) -> None:
    """Increment job enqueue counter."""

    QUEUE_ENQUEUED.labels(queue=queue_name, priority=priority).inc()


def record_retry_scheduled(queue_name: str) -> None:
    """Record that a retry has been scheduled."""

    RETRY_SCHEDULED.labels(queue=queue_name).inc()


def record_dead_letter(queue_name: str) -> None:
    """Increment dead letter counter."""

    DEAD_LETTER_TOTAL.labels(queue=queue_name).inc()


def observe_job_duration(queue_name: str, duration: float, *, result: str) -> None:
    """Record job duration histogram entry."""

    JOB_DURATION_SECONDS.labels(queue=queue_name, result=result).observe(duration)


def update_queue_depth(queue_name: str, depth: int) -> None:
    """Update queue depth gauge."""

    QUEUE_DEPTH.labels(queue=queue_name).set(depth)


def update_workers_busy(queue_name: str, count: int) -> None:
    """Update busy worker gauge."""

    WORKERS_BUSY.labels(queue=queue_name).set(count)
