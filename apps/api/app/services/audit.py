import asyncio, hashlib, json, logging, uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID
from collections import deque
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from apps.api.app.config_t3 import settings
from apps.api.app.models.audit import AuditEvent

logger = logging.getLogger(__name__)


def _db_session():
    from apps.api.app.db import get_db_session

    return contextmanager(get_db_session)()


class AuditEventType:
    ENQUEUED="ENQUEUED"; STARTED="STARTED"; EXTRACTED="EXTRACTED"; EXPORTED="EXPORTED"
    ERROR="ERROR"; DELETION_REQUESTED="DELETION_REQUESTED"; DELETION_COMPLETED="DELETION_COMPLETED"
    CANCELLED="CANCELLED"; PARTIAL_CANCEL="PARTIAL_CANCEL"

def _idk(job_id: UUID, event_type: str, trace_id: Optional[UUID], user_id: Optional[str], ip: Optional[str], md: Dict[str, Any], ts: datetime)->str:
    payload = {"job_id": str(job_id), "event_type": event_type, "trace_id": str(trace_id) if trace_id else "", "user_id": user_id or "", "ip": ip or "", "metadata": md or {}, "ts": ts.replace(microsecond=0).isoformat()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True,separators=(",",":")).encode()).hexdigest()

_redis = None
async def _redis_client():
    global _redis
    if _redis is None and settings.audit_durable_mode == "redis":
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(settings.redis_url or "redis://localhost:6379/0", encoding="utf-8", decode_responses=True)
    return _redis

class AuditBatcher:
    def __init__(self, batch_size:int=50, flush_interval_ms:int=1000, max_queue_size:int=10000):
        self.batch_size=batch_size; self.flush_interval_ms=flush_interval_ms; self.max_queue_size=max_queue_size
        self.queue: deque = deque(); self.lock = asyncio.Lock(); self._task: Optional[asyncio.Task]=None; self._running=False

    async def start(self):
        if self._running: return
        self._running=True
        self._task=asyncio.create_task(self._loop())

    async def stop(self):
        self._running=False
        if self._task: self._task.cancel()
        try:
            if self._task: await self._task
        except asyncio.CancelledError:
            pass
        await self._flush()

    async def add_event(self, job_id: UUID, event_type:str, trace_id:Optional[UUID]=None, user_id:Optional[str]=None, ip_address:Optional[str]=None, metadata:Optional[Dict[str,Any]]=None)->bool:
        ts = datetime.now(timezone.utc)
        event = {
            "id": uuid.uuid4(),
            "job_id": job_id,
            "event_type": event_type,
            "trace_id": str(trace_id) if trace_id else None,
            "user_id": user_id,
            "ip_address": ip_address,
            "metadata": metadata or {},
            "created_at": ts,
        }
        event["idempotency_key"] = _idk(job_id, event_type, trace_id, user_id, ip_address, event["metadata"], ts)

        if settings.audit_durable_mode == "redis":
            rc = await _redis_client()
            if not rc: return False
            await rc.xadd("audit:events", {"payload": json.dumps({**event, "id": str(event["id"])}, default=str)})
            return True

        async with self.lock:
            if len(self.queue) >= self.max_queue_size:
                logger.error("Audit queue full; dropping event"); return False
            self.queue.append(event)
            if len(self.queue) >= self.batch_size:
                asyncio.create_task(self._flush())
            return True

    async def _loop(self):
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval_ms/1000.0)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("audit flush loop error")

    async def _flush(self):
        if settings.audit_durable_mode == "redis": return
        async with self.lock:
            if not self.queue: return
            batch=[]
            while self.queue and len(batch) < self.batch_size:
                batch.append(self.queue.popleft())
        if not batch: return
        try:
            with _db_session() as s:
                stmt = (
                    pg_insert(AuditEvent.__table__)
                    .values(batch)
                    .on_conflict_do_nothing(index_elements=[AuditEvent.idempotency_key])
                )
                s.execute(stmt)
                s.commit()
        except Exception:
            logger.exception("failed to flush audit batch; requeue")
            async with self.lock: self.queue.extendleft(reversed(batch))

_batcher: Optional[AuditBatcher] = None
def get_audit_batcher()->AuditBatcher:
    global _batcher
    if _batcher is None:
        _batcher=AuditBatcher(settings.audit_batch_size, settings.audit_flush_interval_ms, settings.audit_max_queue_size)
    return _batcher

async def log_audit_event(**kw)->bool:
    return await get_audit_batcher().add_event(**kw)

async def get_audit_trail(job_id: UUID, limit:int=100)->List[Dict[str,Any]]:
    with _db_session() as s:
        res = s.execute(
            select(AuditEvent)
            .where(AuditEvent.job_id == job_id)
            .order_by(AuditEvent.created_at)
            .limit(limit)
        )
        out=[]
        for e in res.scalars().all():
            out.append({"id":str(e.id),"event_type":e.event_type,"user_id":e.user_id,"ip_address":e.ip_address,"trace_id":str(e.trace_id) if e.trace_id else None,"metadata":e.metadata,"created_at":e.created_at.isoformat()})
        return out
