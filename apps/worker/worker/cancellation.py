from apps.worker.worker.services import get_job, mark_job_cancelled
import asyncio
import logging
from contextlib import asynccontextmanager

log=logging.getLogger(__name__)

class JobCancelledException(Exception):
    pass

async def check_cancellation(job_id: str):
    job=await get_job(job_id)
    if job and job["cancellation_requested"]:
        await mark_job_cancelled(job_id)
        raise JobCancelledException(f"Job {job_id} was cancelled")

@asynccontextmanager
async def cancellation_checkpoint(job_id: str, message: str="checkpoint"):
    await check_cancellation(job_id)
    log.debug(f"Checkpoint {message} for job {job_id}")
    yield
    await check_cancellation(job_id)
