"""
Document processing routes for queue-based processing.
"""
import logging
import time
import os
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from ..services import DocumentService

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
        
        # Check if queue is available
        redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
        if not redis_url:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "QUEUE_UNAVAILABLE",
                    "message": "Processing queue not available"
                }
            )
        
        # Import here to avoid circular imports
        try:
            from celery import Celery
            celery_app = Celery('ledger_lift_worker', broker=redis_url)
            
            # Queue the document for processing
            result = celery_app.send_task(
                'worker.tasks.process_document_task',
                args=[doc_id],
                queue='document_processing'
            )
            
            processing_time = time.time() - start_time
            
            logger.info(f"Document queued for processing: {doc_id} (task_id: {result.id})")
            
            return {
                "success": True,
                "document_id": doc_id,
                "task_id": result.id,
                "message": "Document queued for processing",
                "processing_time_ms": round(processing_time * 1000, 2)
            }
            
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "QUEUE_UNAVAILABLE",
                    "message": "Celery not available"
                }
            )
        except Exception as queue_error:
            logger.error(f"Failed to queue document {doc_id}: {queue_error}")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "QUEUE_ERROR",
                    "message": "Failed to queue document for processing"
                }
            )
        
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
        # Check if queue is available
        redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
        if not redis_url:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "QUEUE_UNAVAILABLE",
                    "message": "Processing queue not available"
                }
            )
        
        try:
            from celery import Celery
            celery_app = Celery('ledger_lift_worker', broker=redis_url)
            
            # Get task result
            result = celery_app.AsyncResult(task_id)
            
            processing_time = time.time() - start_time
            
            return {
                "task_id": task_id,
                "status": result.status,
                "ready": result.ready(),
                "successful": result.successful() if result.ready() else None,
                "failed": result.failed() if result.ready() else None,
                "result": result.result if result.ready() else None,
                "processing_time_ms": round(processing_time * 1000, 2)
            }
            
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "QUEUE_UNAVAILABLE",
                    "message": "Celery not available"
                }
            )
        except Exception as queue_error:
            logger.error(f"Failed to get task status for {task_id}: {queue_error}")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "QUEUE_ERROR",
                    "message": "Failed to get task status"
                }
            )
        
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