import uuid
import logging
import time
from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field, validator
from ..aws import s3_manager
from ..settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["uploads"])

class PresignRequest(BaseModel):
    filename: str
    content_type: str = Field(alias="content_type")
    file_size: int
    
    @validator('filename')
    def validate_filename(cls, v):
        if not v:
            raise ValueError('Filename cannot be empty')
        if len(v) > 255:
            raise ValueError('Filename too long (max 255 characters)')
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError('Invalid filename: contains path traversal characters')
        if v.startswith('.') or v.endswith('.'):
            raise ValueError('Invalid filename: cannot start or end with period')
        # Check for control characters
        if any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError('Invalid filename: contains control characters')
        return v
    
    @validator('content_type')
    def validate_content_type(cls, v):
        if not v:
            raise ValueError('Content type cannot be empty')
        allowed = {
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        }
        if v not in allowed:
            raise ValueError(f'Unsupported content type. Allowed: {", ".join(sorted(allowed))}')
        return v
    
    @validator('file_size')
    def validate_file_size(cls, v):
        if v <= 0:
            raise ValueError('File size must be positive')
        if v > settings.max_file_size:
            raise ValueError(f'File too large. Max: {settings.max_file_size:,} bytes ({settings.max_file_size // (1024*1024)}MB)')
        return v

class PresignResponse(BaseModel):
    key: str
    url: str
    expires_in: int
    upload_id: str

@router.post("/v1/uploads/presign", response_model=PresignResponse)
def presign_upload(
    req: PresignRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    """Generate presigned URL for file upload with comprehensive validation and error handling."""
    start_time = time.time()
    request_id = str(uuid.uuid4())
    
    logger.info(f"Presign request started: {request_id}", extra={
        "request_id": request_id,
        "filename": req.filename,
        "content_type": req.content_type,
        "file_size": req.file_size,
        "idempotency_key": idempotency_key
    })
    
    try:
        # Input validation (already handled by Pydantic, but add runtime checks)
        if not req.filename.strip():
            raise HTTPException(
                status_code=400,
                detail={"error": "INVALID_INPUT", "message": "Filename cannot be empty or whitespace"}
            )
        
        # Sanitize filename more aggressively
        clean_filename = "".join(c for c in req.filename if c.isalnum() or c in '.-_')
        if not clean_filename:
            clean_filename = "unnamed_file"
        
        # Create deterministic key with upload ID for tracking
        upload_id = str(uuid.uuid4())
        key = f"raw/{upload_id}-{clean_filename}"
        
        # Check S3 health before generating URL
        s3_health = s3_manager.health_check()
        if s3_health.get('status') != 'healthy':
            logger.error(f"S3 unhealthy during presign request {request_id}: {s3_health.get('error')}")
            raise HTTPException(
                status_code=503,
                detail={"error": "SERVICE_UNAVAILABLE", "message": "Storage service temporarily unavailable"}
            )
        
        # Generate presigned URL with timeout
        try:
            url = s3_manager.generate_presigned_url(
                key, 
                req.content_type, 
                req.file_size, 
                settings.presign_ttl
            )
        except Exception as s3_error:
            logger.error(f"S3 presign failed for request {request_id}: {s3_error}")
            raise HTTPException(
                status_code=503,
                detail={"error": "STORAGE_ERROR", "message": "Failed to generate upload URL"}
            )
        
        processing_time = time.time() - start_time
        logger.info(f"Presign request completed: {request_id} in {processing_time:.3f}s", extra={
            "request_id": request_id,
            "upload_id": upload_id,
            "key": key,
            "processing_time_ms": round(processing_time * 1000, 2)
        })
        
        return {
            "key": key,
            "url": url,
            "expires_in": settings.presign_ttl,
            "upload_id": upload_id
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Unexpected error in presign request {request_id}: {e}", extra={
            "request_id": request_id,
            "error_type": type(e).__name__,
            "processing_time_ms": round(processing_time * 1000, 2)
        })
        raise HTTPException(
            status_code=500,
            detail={"error": "INTERNAL_ERROR", "message": "Internal server error"}
        )
