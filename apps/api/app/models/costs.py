from sqlalchemy import Column, String, Integer, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

class CostRecord:
    __tablename__ = 'cost_records'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(String(255), nullable=True, index=True)
    provider = Column(String(50), nullable=False)
    pages = Column(Integer, nullable=False)
    cost_cents = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default='PENDING')
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
