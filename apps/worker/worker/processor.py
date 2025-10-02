from apps.worker.worker.cancellation import cancellation_checkpoint, JobCancelledException
from apps.worker.worker.services import get_job, mark_job_completed, mark_job_failed, update_job_schedules
from apps.worker.worker.ocr import estimate_page_count, extract_schedules
from apps.worker.worker.costs import record_job_cost, mark_cost_success, mark_cost_failed
import logging

log=logging.getLogger(__name__)

async def process_job(job_id: str):
    try:
        job=await get_job(job_id)
        if not job:
            log.error(f"Job {job_id} not found")
            return
        
        async with cancellation_checkpoint(job_id, "before_ocr"):
            page_count=await estimate_page_count(job_id)
            await record_job_cost(job_id, page_count)
        
        async with cancellation_checkpoint(job_id, "before_extraction"):
            schedules=await extract_schedules(job_id, page_count)
            await update_job_schedules(job_id, schedules)
        
        async with cancellation_checkpoint(job_id, "before_completion"):
            await mark_cost_success(job_id)
            await mark_job_completed(job_id)
        
        log.info(f"Job {job_id} completed successfully")
    
    except JobCancelledException:
        log.info(f"Job {job_id} was cancelled")
        await mark_cost_failed(job_id)
    except Exception as e:
        log.exception(f"Job {job_id} failed: {e}")
        await mark_job_failed(job_id, str(e))
        await mark_cost_failed(job_id)
