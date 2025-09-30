"""RQ job handlers for Ledger Lift."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from apps.worker.config import settings
from apps.worker.infra.redis import get_redis_connection, is_emergency_stopped
from apps.worker.metrics import observe_job_duration
from apps.worker.queues import QueueNames
from apps.worker.worker.services import DocumentProcessor, ProcessingError

try:
    from apps.api.app.progress import write_progress_snapshot
except ImportError:  # pragma: no cover - API package should be available
    def write_progress_snapshot(job_id: str, snapshot: Dict[str, Any], **_: Any) -> Dict[str, Any]:
        return {"job_id": job_id, **snapshot}

logger = logging.getLogger(__name__)


class RetryableJobError(Exception):
    """Raised when a job should be retried."""


def process_document_job(document_id: str, job_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Process a document with retry semantics."""

    connection = get_redis_connection()
    if is_emergency_stopped(connection):
        raise RuntimeError("Emergency stop engaged")

    job_id = job_payload.get("job_id")
    priority = job_payload.get("priority", settings.rq_default_queue)
    queues = QueueNames()
    queue_name = {
        "high": queues.high,
        "low": queues.low,
        "default": queues.default,
    }.get(priority, queues.default)
    start_time = time.time()

    write_progress_snapshot(
        job_id,
        {
            "state": "processing",
            "document_id": document_id,
            "priority": priority,
        },
        connection=connection,
    )

    processor = DocumentProcessor()
    try:
        timeout_seconds = max(1, settings.parse_timeout_ms // 1000)
        result = processor.process_document(document_id, timeout_seconds=timeout_seconds)
        duration = time.time() - start_time
        observe_job_duration(queue_name, duration, result="success")
        write_progress_snapshot(
            job_id,
            {
                "state": "completed",
                "document_id": document_id,
                "priority": priority,
                "duration": duration,
            },
            connection=connection,
        )
        return {
            "document_id": document_id,
            "success": True,
            "duration": duration,
            "result": result,
        }
    except ProcessingError as exc:
        # Processing errors should be retried based on RQ Retry policy.
        duration = time.time() - start_time
        observe_job_duration(queue_name, duration, result="retry")
        write_progress_snapshot(
            job_id,
            {
                "state": "retrying",
                "document_id": document_id,
                "priority": priority,
                "error": str(exc),
            },
            connection=connection,
        )
        raise RetryableJobError(str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        duration = time.time() - start_time
        observe_job_duration(queue_name, duration, result="failed")
        write_progress_snapshot(
            job_id,
            {
                "state": "failed",
                "document_id": document_id,
                "priority": priority,
                "error": str(exc),
            },
            connection=connection,
        )
        raise
