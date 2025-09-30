"""Document processing routes for queue-based processing."""
import logging
import time

from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from ..services import DocumentService
from apps.api.config import settings as api_settings
from apps.api.infra.redis import get_redis_connection, is_emergency_stopped
from apps.api.app.jobs import JobPayload
from apps.api.app.progress import write_progress_snapshot
from apps.api.metrics import record_enqueue, record_enqueue_failure
from apps.worker.queues import enqueue_with_retry

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["processing"])

@router.post("/v1/documents/{doc_id}/process")
@limiter.limit("5/minute")
def trigger_document_processing(request: Request, doc_id: str):
    """Trigger document processing via queue."""
    start_time = time.time()
    
    # Input validation
    if not doc_id or not doc_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_INPUT",
                "message": "Document ID cannot be empty"
            }
        )
    
    doc_id = doc_id.strip()
    if len(doc_id) > 100:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_INPUT",
                "message": "Document ID too long"
            }
        )
    
    logger.info(f"Triggering document processing: {doc_id}")
    
    try:
        # Check if document exists
        doc_result = DocumentService.get_document(doc_id)
        if not doc_result.success or not doc_result.data:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "NOT_FOUND",
                    "message": "Document not found"
                }
            )

        if not api_settings.features_t1_queue:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "QUEUE_DISABLED",
                    "message": "Queueing is temporarily disabled"
                }
            )

        connection = get_redis_connection()
        if is_emergency_stopped(connection):
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "EMERGENCY_STOP",
                    "message": "Processing temporarily halted"
                }
            )

        priority = request.query_params.get("priority", "default").lower()
        if priority not in {"high", "default", "low"}:
            priority = "default"

        payload = JobPayload(
            document_id=doc_id,
            priority=priority,
            user_id=request.headers.get("x-user-id")
        )

        try:
            job = enqueue_with_retry(
                "worker.jobs.process_document_job",
                kwargs={
                    "document_id": doc_id,
                    "job_payload": payload.to_dict()
                },
                priority=priority,
                job_id=payload.job_id,
                metadata=payload.redis_metadata(),
                job_timeout=max(1, api_settings.parse_timeout_ms // 1000),
                connection=connection
            )
        except RuntimeError as queue_error:
            logger.error("Failed to enqueue job due to emergency stop", exc_info=True)
            record_enqueue_failure(priority)
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "QUEUE_HALTED",
                    "message": str(queue_error)
                }
            ) from queue_error
        except Exception as queue_error:
            logger.error(f"Failed to queue document {doc_id}: {queue_error}")
            record_enqueue_failure(priority)
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "QUEUE_ERROR",
                    "message": "Failed to queue document for processing"
                }
            ) from queue_error

        processing_time = time.time() - start_time
        write_progress_snapshot(
            job.id,
            {
                "state": "queued",
                "status": "queued",
                "document_id": doc_id,
                "priority": priority,
                "progress": 0,
            },
            connection=connection,
        )
        record_enqueue(job.origin or "default", priority)

        logger.info(
            "Document queued for processing",
            extra={"document_id": doc_id, "job_id": job.id, "priority": priority}
        )

        return {
            "success": True,
            "document_id": doc_id,
            "task_id": job.id,
            "queue": job.origin,
            "message": "Document queued for processing",
            "processing_time_ms": round(processing_time * 1000, 2)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Unexpected error triggering processing for {doc_id}: {e}", extra={
            "document_id": doc_id,
            "error_type": type(e).__name__,
            "processing_time_ms": round(processing_time * 1000, 2)
        })
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Internal server error"
            }
        )

@router.get("/v1/tasks/{task_id}/status")
def get_task_status(task_id: str):
    """Get the status of a processing task."""
    start_time = time.time()
    
    # Input validation
    if not task_id or not task_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_INPUT",
                "message": "Task ID cannot be empty"
            }
        )
    
    task_id = task_id.strip()
    
    try:
        connection = get_redis_connection()

        try:
            from rq.job import Job
            from rq.exceptions import NoSuchJobError
        except ImportError as exc:  # pragma: no cover - should always be available
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "QUEUE_UNAVAILABLE",
                    "message": "RQ not available"
                }
            ) from exc

        try:
            job = Job.fetch(task_id, connection=connection)
        except NoSuchJobError:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "NOT_FOUND",
                    "message": "Task not found"
                }
            )

        processing_time = time.time() - start_time
        status = job.get_status()
        return {
            "task_id": task_id,
            "status": status,
            "result": job.result if job.is_finished else None,
            "failed": job.is_failed,
            "successful": job.is_finished and not job.is_failed,
            "meta": job.meta,
            "processing_time_ms": round(processing_time * 1000, 2)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Unexpected error getting task status for {task_id}: {e}", extra={
            "task_id": task_id,
            "error_type": type(e).__name__,
            "processing_time_ms": round(processing_time * 1000, 2)
        })
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Internal server error"
            }
        )