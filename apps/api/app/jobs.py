"""Job model used when enqueuing work."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

SCHEMA_VERSION = 1
JOB_VERSION = 1


def _default_timestamp() -> datetime:
    return datetime.now(timezone.utc)


def _generate_job_id() -> str:
    return str(uuid4())


@dataclass(slots=True)
class JobPayload:
    """Payload persisted to Redis queues."""

    document_id: str
    priority: str = "default"
    user_id: Optional[str] = None
    created_at: datetime = field(default_factory=_default_timestamp)
    schema_version: int = SCHEMA_VERSION
    version: int = JOB_VERSION
    p95_hint_ms: Optional[int] = None
    content_hashes: List[str] = field(default_factory=list)
    job_id: str = field(default_factory=_generate_job_id)

    def to_dict(self) -> Dict[str, object]:
        """Convert payload to a serializable dictionary."""

        return {
            "job_id": self.job_id,
            "document_id": self.document_id,
            "priority": self.priority,
            "user_id": self.user_id,
            "p95_hint_ms": self.p95_hint_ms,
            "content_hashes": list(self.content_hashes),
            "created_at": self.created_at.isoformat(),
            "version": self.version,
            "schema_version": self.schema_version,
        }

    def redis_metadata(self) -> Dict[str, object]:
        """Return metadata for RQ job tracking."""

        return {
            "version": self.version,
            "schema_version": self.schema_version,
            "priority": self.priority,
            "document_id": self.document_id,
            "user_id": self.user_id,
        }
