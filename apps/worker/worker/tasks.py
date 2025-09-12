"""
Celery tasks for document processing with comprehensive error handling and monitoring.
"""
import logging
import time
from typing import Dict, Any, Optional
from celery import Celery
from celery.exceptions import Retry, WorkerLostError
from .services import DocumentProcessor
from .database import WorkerDatabase
from .models import ProcessingStatus, EventType

logger = logging.getLogger(__name__)

# Configure Celery
celery_app = Celery(
    'ledger_lift_worker',
    broker='redis://redis:6379/0',
    backend='redis://redis:6379/0',
    include=['worker.tasks']
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,  # 30 minutes
    task_soft_time_limit=1500,  # 25 minutes
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_disable_rate_limits=True,
    task_reject_on_worker_lost=True,
    task_ignore_result=False,
    result_expires=3600,  # 1 hour
    task_routes={
        'worker.tasks.process_document_task': {'queue': 'document_processing'},
        'worker.tasks.health_check_task': {'queue': 'health_checks'},
    },
    task_default_queue='document_processing',
    task_default_exchange='document_processing',
    task_default_exchange_type='direct',
    task_default_routing_key='document_processing',
)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_document_task(self, doc_id: str) -> Dict[str, Any]:
    """
    Process a document with comprehensive error handling and retry logic.
    
    Args:
        doc_id: Document ID to process
        
    Returns:
        Dictionary with processing results and metadata
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting document processing task: {doc_id} (task_id: {task_id})")
    
    try:
        # Initialize processor
        processor = DocumentProcessor()
        
        # Process the document
        result = processor.process_document(doc_id, timeout_seconds=1500)  # 25 minutes
        
        processing_time = time.time() - start_time
        
        logger.info(f"Document processing completed successfully: {doc_id} in {processing_time:.2f}s")
        
        return {
            'success': True,
            'document_id': doc_id,
            'task_id': task_id,
            'processing_time': processing_time,
            'result': result
        }
        
    except Exception as exc:
        processing_time = time.time() - start_time
        error_msg = f"Document processing failed: {str(exc)}"
        
        logger.error(f"Document processing failed: {doc_id} - {error_msg}", exc_info=True)
        
        # Update document status to failed
        try:
            db = WorkerDatabase()
            db.update_document_status(doc_id, ProcessingStatus.FAILED, error_msg)
            db.log_event(
                doc_id, 
                EventType.PROCESSING_FAILED, 
                f"Task failed: {error_msg}",
                f'{{"task_id": "{task_id}", "processing_time": {processing_time:.2f}}}'
            )
        except Exception as db_error:
            logger.error(f"Failed to update document status: {db_error}")
        
        # Determine if we should retry
        if self.request.retries < self.max_retries:
            retry_delay = 60 * (2 ** self.request.retries)  # Exponential backoff
            logger.info(f"Retrying document processing: {doc_id} in {retry_delay}s (attempt {self.request.retries + 1}/{self.max_retries})")
            
            raise self.retry(
                exc=exc, 
                countdown=retry_delay,
                max_retries=self.max_retries
            )
        else:
            logger.error(f"Document processing failed permanently: {doc_id} after {self.max_retries} retries")
            
            return {
                'success': False,
                'document_id': doc_id,
                'task_id': task_id,
                'error': error_msg,
                'processing_time': processing_time,
                'retries_exhausted': True
            }

@celery_app.task(bind=True, max_retries=1)
def health_check_task(self) -> Dict[str, Any]:
    """
    Health check task to monitor worker status.
    
    Returns:
        Dictionary with health status information
    """
    start_time = time.time()
    
    try:
        processor = DocumentProcessor()
        health_status = processor.health_check()
        
        processing_time = time.time() - start_time
        
        return {
            'success': True,
            'health_status': health_status,
            'processing_time': processing_time,
            'timestamp': time.time()
        }
        
    except Exception as exc:
        processing_time = time.time() - start_time
        error_msg = f"Health check failed: {str(exc)}"
        
        logger.error(f"Health check failed: {error_msg}", exc_info=True)
        
        return {
            'success': False,
            'error': error_msg,
            'processing_time': processing_time,
            'timestamp': time.time()
        }

@celery_app.task(bind=True, max_retries=2)
def batch_process_documents_task(self, doc_ids: list) -> Dict[str, Any]:
    """
    Process multiple documents in batch.
    
    Args:
        doc_ids: List of document IDs to process
        
    Returns:
        Dictionary with batch processing results
    """
    task_id = self.request.id
    start_time = time.time()
    
    logger.info(f"Starting batch processing: {len(doc_ids)} documents (task_id: {task_id})")
    
    results = {
        'successful': [],
        'failed': [],
        'total': len(doc_ids),
        'task_id': task_id
    }
    
    try:
        for doc_id in doc_ids:
            try:
                # Process each document
                result = process_document_task.delay(doc_id)
                results['successful'].append({
                    'document_id': doc_id,
                    'task_id': result.id
                })
            except Exception as exc:
                logger.error(f"Failed to queue document {doc_id}: {exc}")
                results['failed'].append({
                    'document_id': doc_id,
                    'error': str(exc)
                })
        
        processing_time = time.time() - start_time
        
        logger.info(f"Batch processing queued: {len(results['successful'])} successful, {len(results['failed'])} failed in {processing_time:.2f}s")
        
        return {
            'success': True,
            'results': results,
            'processing_time': processing_time
        }
        
    except Exception as exc:
        processing_time = time.time() - start_time
        error_msg = f"Batch processing failed: {str(exc)}"
        
        logger.error(f"Batch processing failed: {error_msg}", exc_info=True)
        
        return {
            'success': False,
            'error': error_msg,
            'results': results,
            'processing_time': processing_time
        }

# Celery signal handlers for monitoring
@celery_app.task(bind=True)
def task_prerun_handler(sender, task_id, task, args, kwargs, **kwds):
    """Handle task pre-run events."""
    logger.info(f"Task starting: {task.name} (task_id: {task_id})")

@celery_app.task(bind=True)
def task_postrun_handler(sender, task_id, task, args, kwargs, retval, state, **kwds):
    """Handle task post-run events."""
    logger.info(f"Task completed: {task.name} (task_id: {task_id}, state: {state})")

@celery_app.task(bind=True)
def task_failure_handler(sender, task_id, exception, traceback, einfo, **kwds):
    """Handle task failure events."""
    logger.error(f"Task failed: {sender.name} (task_id: {task_id}) - {exception}")

# Utility functions for task management
def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Get the status of a specific task."""
    try:
        result = celery_app.AsyncResult(task_id)
        return {
            'task_id': task_id,
            'status': result.status,
            'result': result.result if result.ready() else None,
            'ready': result.ready(),
            'successful': result.successful() if result.ready() else None,
            'failed': result.failed() if result.ready() else None
        }
    except Exception as exc:
        logger.error(f"Failed to get task status for {task_id}: {exc}")
        return None

def get_queue_stats() -> Dict[str, Any]:
    """Get queue statistics."""
    try:
        inspect = celery_app.control.inspect()
        
        active_tasks = inspect.active()
        scheduled_tasks = inspect.scheduled()
        reserved_tasks = inspect.reserved()
        
        return {
            'active_tasks': active_tasks,
            'scheduled_tasks': scheduled_tasks,
            'reserved_tasks': reserved_tasks,
            'timestamp': time.time()
        }
    except Exception as exc:
        logger.error(f"Failed to get queue stats: {exc}")
        return {'error': str(exc), 'timestamp': time.time()}

def purge_queue(queue_name: str = 'document_processing') -> bool:
    """Purge all tasks from a specific queue."""
    try:
        celery_app.control.purge()
        logger.info(f"Purged queue: {queue_name}")
        return True
    except Exception as exc:
        logger.error(f"Failed to purge queue {queue_name}: {exc}")
        return False