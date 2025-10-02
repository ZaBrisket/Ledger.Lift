from sqlalchemy import Column, String, TIMESTAMP, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func, text
import uuid

class AuditEvent:
    __tablename__ = 'audit_events'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    user_id = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    trace_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    idempotency_key = Column(String(64), nullable=False)
    metadata = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
