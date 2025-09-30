"""Prometheus instrumentation helpers for worker processes."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

JOB_DURATION_SECONDS = Histogram(
    "ledger_lift_worker_job_duration_seconds",
    "Duration of jobs processed by worker processes.",
    labelnames=("queue", "outcome"),
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300, 600, 900, 1200, 1800),
)

QUEUE_ENQUEUED_TOTAL = Counter(
    "ledger_lift_worker_enqueued_total",
    "Jobs enqueued by worker side helpers.",
    labelnames=("queue",),
)

QUEUE_DLQ_TOTAL = Counter(
    "ledger_lift_worker_dlq_total",
    "Jobs moved to the dead letter queue.",
    labelnames=("queue",),
)

QUEUE_DEPTH_GAUGE = Gauge(
    "ledger_lift_worker_queue_depth",
    "Queue depth observed by worker instances.",
    labelnames=("queue",),
)

BUSY_WORKERS_GAUGE = Gauge(
    "ledger_lift_worker_busy",
    "Number of busy workers.",
)


def observe_enqueue(queue_name: str) -> None:
    QUEUE_ENQUEUED_TOTAL.labels(queue=queue_name).inc()


def observe_dlq(queue_name: str) -> None:
    QUEUE_DLQ_TOTAL.labels(queue=queue_name).inc()


def observe_duration(queue_name: str, outcome: str, seconds: float) -> None:
    JOB_DURATION_SECONDS.labels(queue=queue_name, outcome=outcome).observe(seconds)


def update_depth(queue_name: str, depth: int) -> None:
    QUEUE_DEPTH_GAUGE.labels(queue=queue_name).set(depth)


def update_busy(count: int) -> None:
    BUSY_WORKERS_GAUGE.set(count)
