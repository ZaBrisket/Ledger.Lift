import asyncio, logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy import select, delete

from apps.api.app.models.costs import CostRecord
from apps.api.app.services.audit import log_audit_event, AuditEventType

log = logging.getLogger(__name__)


def _db_session():
    from apps.api.app.db import get_db_session

    return contextmanager(get_db_session)()

class ManifestStatus: 
    PENDING="PENDING"
    DELETING="DELETING"
    COMPLETED="COMPLETED"
    FAILED="FAILED"

async def _artifacts(job)->List[Dict[str,str]]:
    out=[]
    for k,t in (("source_key","incoming"),("processed_key","processed"),("export_key","export")):
        key=getattr(job,k,None)
        if key: out.append({"type":t,"key":key,"bucket":getattr(job,"bucket","default")})
    return out

async def initiate_job_deletion(job_id: UUID, user_id: Optional[str]=None, trace_id: Optional[UUID]=None)->Dict[str,Any]:
    with _db_session() as s:
        from sqlalchemy import text
        res=s.execute(text("SELECT id, status, source_key, processed_key, export_key, bucket FROM jobs WHERE id = :id FOR UPDATE"), {"id": str(job_id)})
        job=res.mappings().first()
        if not job: return {"success":False,"error":"Job not found"}

        # Cancel if processing
        if job.get("status") in ("QUEUED","PROCESSING"):
            s.execute(text("UPDATE jobs SET cancellation_requested = true WHERE id = :id"), {"id": str(job_id)})
        
        # Create manifest
        artifacts = []
        for k,t in (("source_key","incoming"),("processed_key","processed"),("export_key","export")):
            key=job.get(k)
            if key: artifacts.append({"type":t,"key":key,"bucket":job.get("bucket","default")})
        
        manifest = {
            "job_id":str(job_id),
            "created_at":datetime.now(timezone.utc).isoformat(),
            "user_id":user_id,
            "artifacts":artifacts,
            "status":ManifestStatus.PENDING
        }
        
        s.execute(text("UPDATE jobs SET deletion_manifest = :manifest WHERE id = :id"),
                   {"manifest": str(manifest).replace("'", '"'), "id": str(job_id)})
        s.commit()
    
    await log_audit_event(job_id=job_id,event_type=AuditEventType.DELETION_REQUESTED,trace_id=trace_id,user_id=user_id,metadata={"manifest_created":True})
    asyncio.create_task(_execute_deletion(job_id))
    return {"success":True,"job_id":str(job_id),"status":ManifestStatus.DELETING}

async def _execute_deletion(job_id: UUID, max_retries:int=3):
    for attempt in range(max_retries):
        try:
            with _db_session() as s:
                from sqlalchemy import text
                res=s.execute(text("SELECT deletion_manifest FROM jobs WHERE id = :id"), {"id": str(job_id)})
                row=res.first()
                if not row or not row[0]: return
                
                import json
                m=json.loads(row[0]) if isinstance(row[0], str) else row[0]
                
                # Delete artifacts (placeholder - implement with actual storage client)
                failed=[]
                for a in m.get("artifacts",[]):
                    try:
                        # TODO: Implement actual storage deletion
                        # await storage.delete_object(bucket=a["bucket"], key=a["key"])
                        pass
                    except Exception as e:
                        log.error("delete fail %s: %s",a.get("key"),e)
                        failed.append(a)
                
                if not failed:
                    s.execute(delete(CostRecord).where(CostRecord.job_id==job_id))
                    s.execute(text("DELETE FROM jobs WHERE id = :id"), {"id": str(job_id)})
                    s.commit()
                    await log_audit_event(job_id=job_id,event_type=AuditEventType.DELETION_COMPLETED,metadata={"artifacts_deleted":len(m.get("artifacts",[]))})
                    return
                else:
                    m["artifacts"]=failed
                    m["status"]=ManifestStatus.FAILED
                    m["last_attempt"]=datetime.now(timezone.utc).isoformat()
                    s.execute(text("UPDATE jobs SET deletion_manifest = :manifest WHERE id = :id"),
                              {"manifest": json.dumps(m), "id": str(job_id)})
                    s.commit()
                    if attempt < max_retries-1: await asyncio.sleep(2**attempt)
        except Exception:
            log.exception("deletion attempt %s failed",attempt+1)
            if attempt < max_retries-1: await asyncio.sleep(2**attempt)

async def sweep_stale_deletions():
    with _db_session() as s:
        from sqlalchemy import text
        res=s.execute(text("SELECT id FROM jobs WHERE deletion_manifest IS NOT NULL"))
        for row in res:
            asyncio.create_task(_execute_deletion(UUID(str(row[0]))))
