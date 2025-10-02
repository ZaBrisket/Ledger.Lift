import logging
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from uuid import UUID
from sqlalchemy import select, func

from apps.api.app.models.costs import CostRecord
from apps.api.app.config_t3 import settings

log=logging.getLogger(__name__)


def _db_session():
    from apps.api.app.db import get_db_session

    return contextmanager(get_db_session)()

async def record_ocr_cost(job_id: UUID, user_id: Optional[str], provider:str, pages:int, cost_per_page_cents:int)->UUID:
    cost = pages*cost_per_page_cents
    if cost > settings.max_job_cost_cents: raise ValueError("Estimated OCR cost exceeds limit")
    with _db_session() as s:
        rec = CostRecord(job_id=job_id,user_id=user_id,provider=provider,pages=pages,cost_cents=cost,status='PENDING',created_at=datetime.now(timezone.utc))
        s.add(rec); s.commit(); s.refresh(rec)
        return rec.id

async def mark_cost_completed(record_id: UUID, success: bool=True):
    with _db_session() as s:
        res=s.execute(select(CostRecord).where(CostRecord.id==record_id))
        rec=res.scalar_one_or_none()
        if rec:
            rec.status='COMPLETED' if success else 'FAILED'
            rec.completed_at=datetime.now(timezone.utc); s.commit()

async def get_user_costs(user_id: str)->Dict[str,Any]:
    with _db_session() as s:
        stmt=select(func.sum(CostRecord.cost_cents).label('tc'), func.sum(CostRecord.pages).label('tp'), func.count(CostRecord.id).label('tj')).where(CostRecord.user_id==user_id, CostRecord.status=='COMPLETED')
        row=s.execute(stmt).one()
        tc=row.tc or 0
        return {'user_id':user_id,'total_cost_cents':tc,'total_cost_dollars':tc/100.0,'total_pages':row.tp or 0,'total_jobs':row.tj or 0}

async def reconcile_costs()->Dict[str,Any]:
    cutoff=datetime.now(timezone.utc)-timedelta(minutes=5)
    with _db_session() as s:
        res=s.execute(select(CostRecord).where(CostRecord.status=='PENDING', CostRecord.created_at < cutoff))
        stale=res.scalars().all()
        div=[{'record_id':str(r.id),'job_id':str(r.job_id),'status':'STALE_PENDING','age_minutes':(datetime.now(timezone.utc)-r.created_at).total_seconds()/60} for r in stale]
        return {'divergences':div,'count':len(div)}
