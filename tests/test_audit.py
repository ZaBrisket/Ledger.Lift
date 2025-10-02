import pytest
from apps.api.app.services.audit import AuditBatcher, _idk
from apps.api.app.models.audit import AuditEvent

@pytest.mark.asyncio
async def test_audit_idempotency_collapse(db_session):
    batcher = AuditBatcher(batch_size=10, flush_interval_ms=5000)
    
    # Same event sent twice with same parameters should collapse to one
    event1 = {"job_id": "job-123", "event_type": "job.started", "user_id": "user-1", "ip_address": "1.2.3.4", "trace_id": "trace-abc", "metadata": {"foo": "bar"}}
    event2 = {"job_id": "job-123", "event_type": "job.started", "user_id": "user-1", "ip_address": "1.2.3.4", "trace_id": "trace-abc", "metadata": {"foo": "bar"}}
    
    idk1 = _idk(event1)
    idk2 = _idk(event2)
    assert idk1 == idk2, "Idempotency keys should match for identical events"
    
    await batcher.add_event(**event1)
    await batcher.add_event(**event2)
    
    # Force flush
    await batcher._flush()
    
    # Check DB has only one event
    result = await db_session.execute("SELECT COUNT(*) FROM audit_events WHERE job_id='job-123'")
    count = result.scalar()
    assert count == 1, "Duplicate events should collapse to one"
