from sqlalchemy import text
from apps.worker.worker.database import async_session_factory
from apps.worker.worker.config import settings
import logging

log=logging.getLogger(__name__)

async def record_job_cost(job_id: str, page_count: int):
    cost_cents=page_count * settings.cost_per_page_cents
    if cost_cents > settings.max_job_cost_cents:
        raise ValueError(f"Job {job_id} cost {cost_cents} cents exceeds max {settings.max_job_cost_cents}")
    
    async with async_session_factory() as session:
        await session.execute(text("INSERT INTO cost_records(job_id,user_id,provider,pages,cost_cents,status) SELECT id,user_id,'ocr',:pages,:cost,'PENDING' FROM jobs WHERE id=:job_id"), {"job_id":job_id,"pages":page_count,"cost":cost_cents})
        await session.commit()
    log.info(f"Recorded cost for job {job_id}: {page_count} pages = {cost_cents} cents")

async def mark_cost_success(job_id: str):
    async with async_session_factory() as session:
        await session.execute(text("UPDATE cost_records SET status='COMPLETED',completed_at=NOW() WHERE job_id=:job_id AND status='PENDING'"), {"job_id":job_id})
        await session.commit()

async def mark_cost_failed(job_id: str):
    async with async_session_factory() as session:
        await session.execute(text("UPDATE cost_records SET status='FAILED',completed_at=NOW() WHERE job_id=:job_id AND status='PENDING'"), {"job_id":job_id})
        await session.commit()
