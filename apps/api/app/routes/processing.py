"""Document processing routes leveraging RQ priority queues."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, HTTPException, Request, status
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job
from rq.worker import Worker
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from apps.api.config import get_api_settings
from apps.api.infra.redis import get_redis_connection
from apps.api.metrics import observe_enqueue, snapshot_progress, update_queue_depth, update_workers_busy
from ..services import DocumentService

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(tags=["processing"])

QUEUE_JOB_NAME = "apps.worker.worker.rq_jobs.process_document_job"


def _queue_name_for_priority(priority: str, settings) -> str:
    mapping = {
        "high": settings.rq_high_queue,
        "default": settings.rq_default_queue,
        "low": settings.rq_low_queue,
    }
    try:
        return mapping[priority]
    except KeyError as exc:  # pragma: no cover - validated earlier
        raise ValueError(f"Unsupported priority: {priority}") from exc


def _build_job_payload(document_id: str, priority: str) -> Dict[str, object]:
    settings = get_api_settings()
    return {
        "version": settings.work_version,
        "schema_version": settings.schema_version,
        "document_id": document_id,
        "priority": priority,
        "user_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "p95_hint_ms": None,
        "content_hashes": [],
    }


def _enqueue_via_celery(document_id: str, start_time: float):
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    try:
        from celery import Celery

        celery_app = Celery("ledger_lift_worker", broker=redis_url)
        result = celery_app.send_task(
            "worker.tasks.process_document_task",
            args=[document_id],
            queue="document_processing",
        )
        duration = time.time() - start_time
        return {
            "success": True,
            "document_id": document_id,
            "task_id": result.id,
            "message": "Document queued for processing",
            "processing_time_ms": round(duration * 1000, 2),
        }
    except ImportError as exc:  # pragma: no cover - legacy path
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "QUEUE_UNAVAILABLE", "message": "Celery not available"},
        ) from exc


@router.post("/v1/documents/{doc_id}/process")
@limiter.limit("5/minute")
def trigger_document_processing(request: Request, doc_id: str):
    """Trigger document processing via RQ priority queues."""

    start_time = time.time()
    if not doc_id or not doc_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_INPUT", "message": "Document ID cannot be empty"},
        )

    doc_id = doc_id.strip()
    if len(doc_id) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_INPUT", "message": "Document ID too long"},
        )

    priority = request.query_params.get("priority", "default").lower()
    if priority not in {"high", "default", "low"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_PRIORITY", "message": f"Unsupported priority '{priority}'"},
        )

    logger.info("Triggering document processing", extra={"document_id": doc_id, "priority": priority})

    doc_result = DocumentService.get_document(doc_id)
    if not doc_result.success or not doc_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Document not found"},
        )

    settings = get_api_settings()
    if not settings.features_t1_queue:
        return _enqueue_via_celery(doc_id, start_time)

    redis_client = get_redis_connection()

    if redis_client.exists("EMERGENCY_STOP"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "QUEUE_HALTED", "message": "Emergency stop engaged"},
        )

    queue_name = _queue_name_for_priority(priority, settings)
    queue = Queue(queue_name, connection=redis_client)

    job_payload = _build_job_payload(doc_id, priority)
    job = queue.enqueue(QUEUE_JOB_NAME, kwargs={"document_id": doc_id, "payload": job_payload})
    job.meta.update(job_payload)
    job.save_meta()

    progress_body = json.dumps(
        {
            "job_id": job.id,
            "status": "queued",
            "progress": 0.0,
            "message": "Queued for processing",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    snapshot_progress(job.id, redis_client, progress_body)

    observe_enqueue(queue.name)
    update_queue_depth(queue.name, queue.count)
    busy_count = sum(1 for worker in Worker.all(connection=redis_client) if worker.state == "busy")
    update_workers_busy(busy_count)

    duration = time.time() - start_time
    logger.info(
        "Document queued",
        extra={"document_id": doc_id, "job_id": job.id, "queue": queue.name, "duration": duration},
    )

    return {
        "success": True,
        "document_id": doc_id,
        "job_id": job.id,
        "queue": queue.name,
        "message": "Document queued for processing",
        "processing_time_ms": round(duration * 1000, 2),
    }


@router.get("/v1/tasks/{task_id}/status")
def get_task_status(task_id: str):
    """Return the status and metadata for a queued job."""

    start_time = time.time()
    if not task_id or not task_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_INPUT", "message": "Task ID cannot be empty"},
        )

    task_id = task_id.strip()
    settings = get_api_settings()
    redis_client = get_redis_connection()

    try:
        if not settings.features_t1_queue:
            raise NoSuchJobError  # Fall back to legacy

        job = Job.fetch(task_id, connection=redis_client)
        progress = redis_client.get(f"job:{task_id}:progress")
        duration = time.time() - start_time
        return {
            "job_id": task_id,
            "status": job.get_status(),
            "meta": job.meta,
            "progress": json.loads(progress) if progress else None,
            "enqueued_at": job.enqueued_at.isoformat() if job.enqueued_at else None,
            "result_ttl": job.result_ttl,
            "processing_time_ms": round(duration * 1000, 2),
        }
    except NoSuchJobError:
        if not settings.features_t1_queue:
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
            try:
                from celery import Celery

                celery_app = Celery("ledger_lift_worker", broker=redis_url)
                result = celery_app.AsyncResult(task_id)
                duration = time.time() - start_time
                return {
                    "task_id": task_id,
                    "status": result.status,
                    "ready": result.ready(),
                    "successful": result.successful() if result.ready() else None,
                    "failed": result.failed() if result.ready() else None,
                    "result": result.result if result.ready() else None,
                    "processing_time_ms": round(duration * 1000, 2),
                }
            except ImportError as exc:  # pragma: no cover - legacy path
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={"error": "QUEUE_UNAVAILABLE", "message": "Celery not available"},
                ) from exc
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "Task not found"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        duration = time.time() - start_time
        logger.error(
            "Unexpected error retrieving job status",
            extra={"task_id": task_id, "error": str(exc), "duration": duration},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "message": "Internal server error"},
        ) from exc


router.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
