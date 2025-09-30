"""RQ job definitions used by Ledger Lift."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict

from rq import get_current_job

from apps.worker.queues import FatalJobError, RetryableJobError, route_to_dlq
from apps.worker.infra.redis import get_redis_connection
from apps.worker.metrics import observe_duration
from apps.worker.config import get_worker_settings
from .services import DocumentProcessor

logger = logging.getLogger(__name__)


PROGRESS_TTL_SECONDS = 3600


def _publish_progress(job_id: str, status: str, progress: float, message: str) -> None:
    redis_client = get_redis_connection()
    payload = json.dumps(
        {
            "job_id": job_id,
            "status": status,
            "progress": progress,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    redis_client.setex(f"job:{job_id}:progress", PROGRESS_TTL_SECONDS, payload)
    redis_client.publish("jobs:progress", payload)


def _check_emergency_stop() -> None:
    redis_client = get_redis_connection()
    if redis_client.exists("EMERGENCY_STOP"):
        raise FatalJobError("Emergency stop engaged")


def process_document_job(document_id: str, *, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Primary worker job for document processing."""

    settings = get_worker_settings()
    job = get_current_job()
    queue_name = job.origin if job else settings.rq_default_queue
    start = time.time()

    if job:
        logger.info("Starting document job", extra={"job_id": job.id, "document_id": document_id, "queue": queue_name})

    _check_emergency_stop()
    _publish_progress(job.id if job else document_id, "starting", 0.0, "Job accepted")

    processor = DocumentProcessor()

    try:
        result = processor.process_document(document_id, timeout_seconds=settings.parse_timeout_ms // 1000)
        duration = time.time() - start
        observe_duration(queue_name, "success", duration)
        _publish_progress(job.id if job else document_id, "completed", 1.0, "Processing complete")

        logger.info(
            "Document job completed",
            extra={
                "job_id": job.id if job else None,
                "document_id": document_id,
                "queue": queue_name,
                "duration": duration,
            },
        )
        return {"document_id": document_id, "result": result, "duration": duration}
    except RetryableJobError:
        duration = time.time() - start
        observe_duration(queue_name, "retry", duration)
        _publish_progress(job.id if job else document_id, "retry", 0.0, "Retry scheduled")
        raise
    except FatalJobError as exc:
        duration = time.time() - start
        observe_duration(queue_name, "fatal", duration)
        if job:
            route_to_dlq(job, reason=str(exc))
        _publish_progress(job.id if job else document_id, "failed", 1.0, str(exc))
        logger.error("Fatal job error", extra={"job_id": job.id if job else None, "error": str(exc)})
        raise
    except Exception as exc:  # pragma: no cover - best effort
        duration = time.time() - start
        observe_duration(queue_name, "error", duration)
        _publish_progress(job.id if job else document_id, "failed", 1.0, str(exc))
        logger.exception("Unhandled job error")
        if job and job.retries_left == 0:
            route_to_dlq(job, reason=str(exc))
        raise RetryableJobError(str(exc)) from exc


def dead_letter_handler(*, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist payload for DLQ inspection."""

    logger.error("Dead letter job", extra={"payload": payload})
    return payload
