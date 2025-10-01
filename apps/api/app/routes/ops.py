"""Operational endpoints for queue monitoring."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, HTTPException
from rq import Queue
from rq.registry import (
    DeferredJobRegistry,
    FailedJobRegistry,
    FinishedJobRegistry,
    ScheduledJobRegistry,
    StartedJobRegistry,
)

from apps.api.config import settings
from apps.api.infra.redis import get_redis_connection, is_emergency_stopped

router = APIRouter(prefix="/ops", tags=["ops"])


def _queue_snapshot(queue_name: str, priority: str, connection) -> Dict[str, int | str]:
    queue = Queue(queue_name, connection=connection)
    registries = {
        "started": StartedJobRegistry(queue_name, connection=connection),
        "scheduled": ScheduledJobRegistry(queue_name, connection=connection),
        "failed": FailedJobRegistry(queue_name, connection=connection),
        "finished": FinishedJobRegistry(queue_name, connection=connection),
        "deferred": DeferredJobRegistry(queue_name, connection=connection),
    }

    return {
        "name": queue_name,
        "priority": priority,
        "size": queue.count(),
        "started": registries["started"].count(),
        "scheduled": registries["scheduled"].count(),
        "failed": registries["failed"].count(),
        "finished": registries["finished"].count(),
        "deferred": registries["deferred"].count(),
    }


@router.get("/queues")
def get_queue_dashboard() -> Dict[str, object]:
    if not settings.enable_ops_endpoints:
        raise HTTPException(
            status_code=403,
            detail={"error": "OPS_ACCESS_FORBIDDEN", "message": "Operations endpoints are disabled"},
        )

    if not settings.features_t1_queue:
        raise HTTPException(
            status_code=503,
            detail={"error": "QUEUE_DISABLED", "message": "Queueing is temporarily disabled"},
        )

    connection = get_redis_connection()
    queue_map: List[Dict[str, int | str]] = []
    for priority, queue_name in (
        ("high", settings.rq_high_queue),
        ("default", settings.rq_default_queue),
        ("low", settings.rq_low_queue),
        ("dead", settings.rq_dlq),
    ):
        snapshot = _queue_snapshot(queue_name, priority, connection)
        queue_map.append(snapshot)

    return {
        "queues": queue_map,
        "emergency_stop": is_emergency_stopped(connection),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
