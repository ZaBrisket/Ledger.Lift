from sqlalchemy import Column, String, Integer, Float, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

class JobSchedule:
    __tablename__ = 'job_schedules'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    confidence = Column(Float, nullable=False, default=0.0)
    row_count = Column(Integer, nullable=False, default=0)
    col_count = Column(Integer, nullable=False, default=0)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
