"""Prometheus metrics primitives for queue orchestration."""
from __future__ import annotations

import time
from typing import Dict

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from fastapi import Response

JOB_DURATION_SECONDS = Histogram(
    "ledger_lift_job_duration_seconds",
    "Processing duration of jobs handled by the API interface.",
    labelnames=("queue", "outcome"),
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300, 600, 900, 1200, 1800),
)

QUEUE_ENQUEUED_TOTAL = Counter(
    "ledger_lift_queue_enqueued_total",
    "Total number of jobs enqueued via the API.",
    labelnames=("queue",),
)

QUEUE_RETRY_TOTAL = Counter(
    "ledger_lift_queue_retries_total",
    "Total number of retries issued by the API.",
    labelnames=("queue",),
)

QUEUE_DEPTH_GAUGE = Gauge(
    "ledger_lift_queue_depth",
    "Number of queued jobs per priority queue as seen by the API.",
    labelnames=("queue",),
)

WORKERS_BUSY_GAUGE = Gauge(
    "ledger_lift_workers_busy",
    "Number of workers reporting busy state.",
)


def observe_enqueue(queue_name: str) -> None:
    """Record a queue enqueue event."""

    QUEUE_ENQUEUED_TOTAL.labels(queue=queue_name).inc()


def observe_retry(queue_name: str) -> None:
    """Record a retry event for a queue."""

    QUEUE_RETRY_TOTAL.labels(queue=queue_name).inc()


def observe_job_duration(queue_name: str, outcome: str, duration_seconds: float) -> None:
    """Record job duration for percentile calculations."""

    JOB_DURATION_SECONDS.labels(queue=queue_name, outcome=outcome).observe(duration_seconds)


def update_queue_depth(queue_name: str, depth: int) -> None:
    """Update the queue depth gauge."""

    QUEUE_DEPTH_GAUGE.labels(queue=queue_name).set(depth)


def update_workers_busy(count: int) -> None:
    """Update busy worker gauge."""

    WORKERS_BUSY_GAUGE.set(count)


def metrics_response() -> Response:
    """Return a Response object containing Prometheus formatted metrics."""

    payload = generate_latest()
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)


def snapshot_progress(job_id: str, redis_client, body: str, ttl_seconds: int = 3600) -> None:
    """Persist and publish job progress for SSE consumption."""

    key = f"job:{job_id}:progress"
    redis_client.setex(key, ttl_seconds, body)
    redis_client.publish("jobs:progress", body)
