import uuid
import logging
import time
import os
import re
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator, root_validator
from ..aws import generate_presigned_url, s3_manager
from ..settings import settings
from ..services import ServiceResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/uploads", tags=["uploads"])

# Constants for validation
ALLOWED_CONTENT_TYPES = {
    'application/pdf': ['.pdf'],
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx']
}

# Filename validation regex - alphanumeric, dots, hyphens, underscores only
FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9._\-]+$')
MAX_FILENAME_LENGTH = 255
MIN_FILE_SIZE = 1  # 1 byte minimum
MAX_FILE_SIZE = settings.max_file_size if hasattr(settings, 'max_file_size') else 100 * 1024 * 1024  # 100MB default

class PresignRequest(BaseModel):
    """Request model for presigned URL generation with comprehensive validation."""
    filename: str = Field(..., min_length=1, max_length=MAX_FILENAME_LENGTH)
    content_type: str = Field(..., alias="content_type")
    file_size: int = Field(..., gt=0)
    
    # Optional fields for enhanced tracking
    client_id: Optional[str] = Field(None, max_length=64)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    @validator('filename')
    def validate_filename(cls, v: str) -> str:
        """Comprehensive filename validation."""
        if not v or v.strip() != v:
            raise ValueError('Filename cannot be empty or contain leading/trailing whitespace')
        
        # Check for path traversal attempts
        if any(dangerous in v for dangerous in ['..', '/', '\\', '\x00']):
            raise ValueError('Filename contains invalid characters')
        
        # Validate against pattern
        if not FILENAME_PATTERN.match(v):
            raise ValueError('Filename must contain only alphanumeric characters, dots, hyphens, and underscores')
        
        # Check for suspicious patterns
        if v.startswith('.') or v.endswith('.'):
            raise ValueError('Filename cannot start or end with a dot')
        
        # Ensure proper extension
        extension = os.path.splitext(v)[1].lower()
        if not extension:
            raise ValueError('Filename must have an extension')
        
        return v
    
    @validator('content_type')
    def validate_content_type(cls, v: str) -> str:
        """Validate content type against allowed list."""
        if v not in ALLOWED_CONTENT_TYPES:
            allowed = list(ALLOWED_CONTENT_TYPES.keys())
            raise ValueError(f'Unsupported content type. Allowed types: {", ".join(allowed)}')
        return v
    
    @validator('file_size')
    def validate_file_size(cls, v: int) -> int:
        """Validate file size is within acceptable range."""
        if v < MIN_FILE_SIZE:
            raise ValueError(f'File too small. Minimum: {MIN_FILE_SIZE} bytes')
        if v > MAX_FILE_SIZE:
            raise ValueError(f'File too large. Maximum: {MAX_FILE_SIZE / 1024 / 1024:.0f}MB')
        return v
    
    @root_validator
    def validate_extension_matches_content_type(cls, values):
        """Ensure file extension matches the declared content type."""
        filename = values.get('filename')
        content_type = values.get('content_type')
        
        if filename and content_type:
            extension = os.path.splitext(filename)[1].lower()
            allowed_extensions = ALLOWED_CONTENT_TYPES.get(content_type, [])
            
            if extension not in allowed_extensions:
                raise ValueError(f'File extension {extension} does not match content type {content_type}')
        
        return values
    
    @validator('client_id')
    def validate_client_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate client ID if provided."""
        if v and not re.match(r'^[a-zA-Z0-9\-_]+$', v):
            raise ValueError('Client ID must be alphanumeric with hyphens/underscores only')
        return v

class PresignResponse(BaseModel):
    """Response model for presigned URL generation."""
    key: str
    url: str
    expires_in: int
    request_id: str
    
    # Additional metadata for client convenience
    max_file_size: int = Field(default=MAX_FILE_SIZE)
    allowed_content_types: list[str] = Field(default_factory=lambda: list(ALLOWED_CONTENT_TYPES.keys()))

class ErrorResponse(BaseModel):
    """Standardized error response."""
    error: str
    error_code: str
    request_id: str
    timestamp: float
    details: Optional[Dict[str, Any]] = None

def get_request_id(request: Request) -> str:
    """Extract or generate request ID for tracking."""
    request_id = request.headers.get('X-Request-ID')
    if not request_id:
        request_id = str(uuid.uuid4())
    return request_id

@router.post("/presign", 
    response_model=PresignResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
        503: {"model": ErrorResponse, "description": "Service unavailable"}
    }
)
async def presign_upload(
    req: PresignRequest,
    request: Request,
    request_id: str = Depends(get_request_id)
) -> PresignResponse:
    """
    Generate a presigned URL for secure file upload to S3.
    
    This endpoint performs comprehensive validation and returns a time-limited
    presigned URL that clients can use to upload files directly to S3.
    """
    start_time = time.time()
    
    # Add request context to logger
    logger.info(f"Presign request received", extra={
        "request_id": request_id,
        "filename": req.filename,
        "content_type": req.content_type,
        "file_size": req.file_size,
        "client_id": req.client_id,
        "client_ip": request.client.host if request.client else "unknown"
    })
    
    try:
        # Sanitize filename - remove any remaining special characters
        base_name = os.path.splitext(req.filename)[0]
        extension = os.path.splitext(req.filename)[1]
        clean_base = "".join(c for c in base_name if c.isalnum() or c in '-_')
        clean_filename = f"{clean_base}{extension}"
        
        # Generate unique key with timestamp for better organization
        timestamp = int(time.time())
        unique_id = str(uuid.uuid4())
        key = f"raw/{timestamp}/{unique_id}-{clean_filename}"
        
        # Set presigned URL expiration
        expires_in = getattr(settings, 'presign_ttl', 900)  # Default 15 minutes
        
        # Check S3 health before generating URL
        s3_health = s3_manager.health_check()
        if s3_health.get('status') != 'healthy':
            logger.error(f"S3 unhealthy during presign request", extra={
                "request_id": request_id,
                "s3_health": s3_health
            })
            raise HTTPException(
                status_code=503,
                detail="Storage service temporarily unavailable"
            )
        
        # Generate presigned URL with timeout
        try:
            url = generate_presigned_url(
                key=key,
                content_type=req.content_type,
                file_size=req.file_size,
                expires_in=expires_in
            )
        except Exception as e:
            if "circuit breaker is open" in str(e).lower():
                raise HTTPException(
                    status_code=503,
                    detail="Storage service temporarily unavailable due to high error rate"
                )
            raise
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Log successful generation
        logger.info(f"Presigned URL generated successfully", extra={
            "request_id": request_id,
            "key": key,
            "expires_in": expires_in,
            "processing_time_ms": round(processing_time * 1000, 2)
        })
        
        # Return response
        return PresignResponse(
            key=key,
            url=url,
            expires_in=expires_in,
            request_id=request_id,
            max_file_size=MAX_FILE_SIZE,
            allowed_content_types=list(ALLOWED_CONTENT_TYPES.keys())
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        # Handle validation errors
        logger.warning(f"Validation error in presign request", extra={
            "request_id": request_id,
            "error": str(e),
            "filename": req.filename
        })
        error_response = ErrorResponse(
            error=str(e),
            error_code="VALIDATION_ERROR",
            request_id=request_id,
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=422,
            content=error_response.dict()
        )
    except Exception as e:
        # Log unexpected errors
        logger.error(f"Unexpected error generating presigned URL", extra={
            "request_id": request_id,
            "error": str(e),
            "error_type": type(e).__name__
        }, exc_info=True)
        
        error_response = ErrorResponse(
            error="Failed to generate upload URL",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
            timestamp=time.time()
        )
        return JSONResponse(
            status_code=500,
            content=error_response.dict()
        )

@router.get("/health")
async def upload_health_check(request_id: str = Depends(get_request_id)) -> Dict[str, Any]:
    """Health check endpoint for upload service."""
    try:
        # Check S3 connectivity
        s3_health = s3_manager.health_check()
        
        return {
            "status": "healthy" if s3_health.get('status') == 'healthy' else "degraded",
            "timestamp": time.time(),
            "request_id": request_id,
            "s3_health": s3_health,
            "allowed_types": list(ALLOWED_CONTENT_TYPES.keys()),
            "max_file_size_mb": MAX_FILE_SIZE / 1024 / 1024
        }
    except Exception as e:
        logger.error(f"Health check failed", extra={
            "request_id": request_id,
            "error": str(e)
        })
        return {
            "status": "unhealthy",
            "timestamp": time.time(),
            "request_id": request_id,
            "error": str(e)
        }
