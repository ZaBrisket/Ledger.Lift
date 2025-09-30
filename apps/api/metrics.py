"""Prometheus metrics helpers for the API service."""
from __future__ import annotations

from prometheus_client import Counter

JOB_ENQUEUED = Counter(
    "ledger_lift_api_jobs_enqueued_total",
    "Number of jobs enqueued via the API",
    ["queue", "priority"],
)

JOB_ENQUEUE_FAILURES = Counter(
    "ledger_lift_api_job_enqueue_failures_total",
    "Number of enqueue attempts that failed",
    ["queue"],
)

JOB_PROGRESS_UPDATES = Counter(
    "ledger_lift_api_job_progress_snapshots_total",
    "Number of progress snapshots stored",
    ["state"],
)


def record_enqueue(queue_name: str, priority: str) -> None:
    """Increment job enqueue counter."""

    JOB_ENQUEUED.labels(queue=queue_name, priority=priority).inc()


def record_enqueue_failure(queue_name: str) -> None:
    """Increment failure counter."""

    JOB_ENQUEUE_FAILURES.labels(queue=queue_name).inc()


def record_progress_snapshot(state: str) -> None:
    """Record that a progress snapshot was persisted."""

    JOB_PROGRESS_UPDATES.labels(state=state or "unknown").inc()
