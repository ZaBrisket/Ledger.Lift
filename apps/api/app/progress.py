"""Server-sent events progress helpers."""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from apps.api.config import settings
from apps.api.infra.redis import get_redis_connection
from apps.api.metrics import record_progress_snapshot

PROGRESS_KEY_TEMPLATE = "job:{job_id}:progress"
PROGRESS_CHANNEL = "jobs:progress"


def _serialize_snapshot(job_id: str, snapshot: Dict[str, Any]) -> str:
    payload = {"job_id": job_id, "timestamp": time.time(), **snapshot}
    return json.dumps(payload, default=str)


def write_progress_snapshot(
    job_id: str,
    snapshot: Dict[str, Any],
    *,
    ttl: Optional[int] = None,
    connection=None,
) -> Dict[str, Any]:
    """Persist job progress into Redis and publish to subscribers."""

    conn = connection or get_redis_connection()
    ttl = ttl or settings.job_progress_ttl_seconds
    serialized = _serialize_snapshot(job_id, snapshot)
    key = PROGRESS_KEY_TEMPLATE.format(job_id=job_id)
    conn.setex(key, ttl, serialized)
    conn.publish(PROGRESS_CHANNEL, serialized)
    record_progress_snapshot(snapshot.get("state", "unknown"))
    return json.loads(serialized)
