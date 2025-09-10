# Shared models between API and Worker
from enum import Enum as PyEnum

class ProcessingStatus(PyEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

class EventType(PyEnum):
    DOCUMENT_UPLOADED = "document_uploaded"
    PROCESSING_STARTED = "processing_started"
    PROCESSING_COMPLETED = "processing_completed"
    PROCESSING_FAILED = "processing_failed"
    EXTRACTION_COMPLETED = "extraction_completed"
    MANUAL_REVIEW_STARTED = "manual_review_started"