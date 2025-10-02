from sqlalchemy import text
from apps.worker.worker.database import async_session_factory
import logging

log=logging.getLogger(__name__)

async def get_job(job_id: str):
    async with async_session_factory() as session:
        result=await session.execute(text("SELECT id,status,cancellation_requested FROM jobs WHERE id=:job_id"), {"job_id":job_id})
        row=result.fetchone()
        if not row:
            return None
        return {"id":row[0],"status":row[1],"cancellation_requested":row[2]}

async def update_job_schedules(job_id: str, schedules: list):
    async with async_session_factory() as session:
        for s in schedules:
            await session.execute(text("INSERT INTO job_schedules(job_id,name,confidence,row_count,col_count) VALUES(:job_id,:name,:conf,:rc,:cc)"), {"job_id":job_id,"name":s["name"],"conf":s["confidence"],"rc":s["row_count"],"cc":s["col_count"]})
        await session.commit()

async def mark_job_cancelled(job_id: str):
    async with async_session_factory() as session:
        await session.execute(text("UPDATE jobs SET status='cancelled' WHERE id=:job_id"), {"job_id":job_id})
        await session.commit()

async def mark_job_failed(job_id: str, error: str):
    async with async_session_factory() as session:
        await session.execute(text("UPDATE jobs SET status='failed' WHERE id=:job_id"), {"job_id":job_id})
        await session.commit()

async def mark_job_completed(job_id: str):
    async with async_session_factory() as session:
        await session.execute(text("UPDATE jobs SET status='completed' WHERE id=:job_id"), {"job_id":job_id})
        await session.commit()
