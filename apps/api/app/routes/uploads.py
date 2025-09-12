import uuid
import logging
import time
import hashlib
import os
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from ..aws import s3_manager
from ..settings import settings
from ..services import DocumentService

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

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

class ChunkUploadRequest(BaseModel):
    filename: str
    content_type: str
    file_size: int
    chunk_number: int
    total_chunks: int
    chunk_size: int
    upload_id: str
    chunk_hash: Optional[str] = None

class ChunkUploadResponse(BaseModel):
    success: bool
    chunk_number: int
    upload_id: str
    message: str

class CompleteUploadRequest(BaseModel):
    upload_id: str
    filename: str
    content_type: str
    file_size: int
    total_chunks: int
    file_hash: Optional[str] = None

class CompleteUploadResponse(BaseModel):
    success: bool
    document_id: str
    upload_id: str
    message: str

@router.post("/v1/uploads/presign", response_model=PresignResponse)
@limiter.limit("10/minute")
def presign_upload(
    request: Request,
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

# In-memory storage for chunk tracking (in production, use Redis)
chunk_storage: Dict[str, Dict[str, Any]] = {}

@router.post("/v1/uploads/chunks", response_model=ChunkUploadResponse)
@limiter.limit("100/minute")
async def upload_chunk(
    request: Request,
    chunk: UploadFile = File(...),
    upload_id: str = Form(...),
    chunk_number: int = Form(...),
    total_chunks: int = Form(...),
    filename: str = Form(...),
    content_type: str = Form(...),
    file_size: int = Form(...),
    chunk_hash: Optional[str] = Form(None)
):
    """Upload a file chunk for resumable uploads."""
    start_time = time.time()
    
    logger.info(f"Chunk upload started: {upload_id}/{chunk_number}")
    
    try:
        # Validate inputs
        if chunk_number < 1 or chunk_number > total_chunks:
            raise HTTPException(
                status_code=400,
                detail={"error": "INVALID_CHUNK", "message": "Invalid chunk number"}
            )
        
        if not upload_id or len(upload_id) > 100:
            raise HTTPException(
                status_code=400,
                detail={"error": "INVALID_UPLOAD_ID", "message": "Invalid upload ID"}
            )
        
        # Initialize upload tracking if first chunk
        if upload_id not in chunk_storage:
            chunk_storage[upload_id] = {
                'filename': filename,
                'content_type': content_type,
                'file_size': file_size,
                'total_chunks': total_chunks,
                'chunks': {},
                'created_at': time.time()
            }
        
        upload_info = chunk_storage[upload_id]
        
        # Validate upload consistency
        if (upload_info['filename'] != filename or 
            upload_info['content_type'] != content_type or
            upload_info['file_size'] != file_size or
            upload_info['total_chunks'] != total_chunks):
            raise HTTPException(
                status_code=400,
                detail={"error": "INCONSISTENT_UPLOAD", "message": "Upload parameters don't match"}
            )
        
        # Read chunk data
        chunk_data = await chunk.read()
        chunk_size = len(chunk_data)
        
        # Validate chunk size
        expected_chunk_size = min(
            settings.max_file_size // total_chunks,
            file_size - (chunk_number - 1) * (file_size // total_chunks)
        )
        
        if chunk_size > expected_chunk_size:
            raise HTTPException(
                status_code=400,
                detail={"error": "CHUNK_TOO_LARGE", "message": "Chunk size exceeds limit"}
            )
        
        # Verify chunk hash if provided
        if chunk_hash:
            calculated_hash = hashlib.sha256(chunk_data).hexdigest()
            if calculated_hash != chunk_hash:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "HASH_MISMATCH", "message": "Chunk hash verification failed"}
                )
        
        # Store chunk
        upload_info['chunks'][str(chunk_number)] = {
            'data': chunk_data,
            'size': chunk_size,
            'hash': chunk_hash,
            'uploaded_at': time.time()
        }
        
        processing_time = time.time() - start_time
        logger.info(f"Chunk uploaded: {upload_id}/{chunk_number} ({chunk_size} bytes) in {processing_time:.3f}s")
        
        return {
            "success": True,
            "chunk_number": chunk_number,
            "upload_id": upload_id,
            "message": f"Chunk {chunk_number}/{total_chunks} uploaded successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Chunk upload failed: {upload_id}/{chunk_number} - {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "INTERNAL_ERROR", "message": "Internal server error"}
        )

@router.post("/v1/uploads/complete", response_model=CompleteUploadResponse)
@limiter.limit("20/minute")
async def complete_upload(request: Request, req: CompleteUploadRequest):
    """Complete a chunked upload by assembling all chunks."""
    start_time = time.time()
    
    logger.info(f"Completing upload: {req.upload_id}")
    
    try:
        # Check if upload exists
        if req.upload_id not in chunk_storage:
            raise HTTPException(
                status_code=404,
                detail={"error": "UPLOAD_NOT_FOUND", "message": "Upload not found"}
            )
        
        upload_info = chunk_storage[req.upload_id]
        
        # Validate request matches stored info
        if (upload_info['filename'] != req.filename or
            upload_info['content_type'] != req.content_type or
            upload_info['file_size'] != req.file_size or
            upload_info['total_chunks'] != req.total_chunks):
            raise HTTPException(
                status_code=400,
                detail={"error": "INCONSISTENT_UPLOAD", "message": "Upload parameters don't match"}
            )
        
        # Check if all chunks are present
        if len(upload_info['chunks']) != req.total_chunks:
            missing_chunks = set(range(1, req.total_chunks + 1)) - set(int(k) for k in upload_info['chunks'].keys())
            raise HTTPException(
                status_code=400,
                detail={"error": "INCOMPLETE_UPLOAD", "message": f"Missing chunks: {sorted(missing_chunks)}"}
            )
        
        # Assemble file from chunks
        file_data = b''
        for chunk_num in range(1, req.total_chunks + 1):
            chunk_info = upload_info['chunks'][str(chunk_num)]
            file_data += chunk_info['data']
        
        # Verify file size
        if len(file_data) != req.file_size:
            raise HTTPException(
                status_code=400,
                detail={"error": "SIZE_MISMATCH", "message": "Assembled file size doesn't match expected size"}
            )
        
        # Verify file hash if provided
        if req.file_hash:
            calculated_hash = hashlib.sha256(file_data).hexdigest()
            if calculated_hash != req.file_hash:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "HASH_MISMATCH", "message": "File hash verification failed"}
                )
        
        # Upload to S3
        upload_id = str(uuid.uuid4())
        s3_key = f"raw/{upload_id}-{req.filename}"
        
        try:
            s3_manager.upload_file(s3_key, file_data, req.content_type)
        except Exception as s3_error:
            logger.error(f"S3 upload failed for {req.upload_id}: {s3_error}")
            raise HTTPException(
                status_code=503,
                detail={"error": "STORAGE_ERROR", "message": "Failed to upload to storage"}
            )
        
        # Register document
        try:
            doc_result = DocumentService.create_document(
                s3_key=s3_key,
                original_filename=req.filename,
                content_type=req.content_type,
                file_size=req.file_size,
                sha256_hash=req.file_hash
            )
            
            if not doc_result.success:
                raise HTTPException(
                    status_code=500,
                    detail={"error": "DOCUMENT_CREATION_FAILED", "message": doc_result.error}
                )
            
            document_id = doc_result.data.id
            
        except Exception as doc_error:
            logger.error(f"Document creation failed for {req.upload_id}: {doc_error}")
            raise HTTPException(
                status_code=500,
                detail={"error": "DOCUMENT_CREATION_FAILED", "message": "Failed to create document record"}
            )
        
        # Clean up chunk storage
        del chunk_storage[req.upload_id]
        
        processing_time = time.time() - start_time
        logger.info(f"Upload completed: {req.upload_id} -> {document_id} in {processing_time:.3f}s")
        
        return {
            "success": True,
            "document_id": document_id,
            "upload_id": req.upload_id,
            "message": "Upload completed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Upload completion failed: {req.upload_id} - {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "INTERNAL_ERROR", "message": "Internal server error"}
        )

@router.get("/v1/uploads/{upload_id}/status")
def get_upload_status(upload_id: str):
    """Get the status of a chunked upload."""
    if upload_id not in chunk_storage:
        raise HTTPException(
            status_code=404,
            detail={"error": "UPLOAD_NOT_FOUND", "message": "Upload not found"}
        )
    
    upload_info = chunk_storage[upload_id]
    uploaded_chunks = len(upload_info['chunks'])
    total_chunks = upload_info['total_chunks']
    
    return {
        "upload_id": upload_id,
        "filename": upload_info['filename'],
        "content_type": upload_info['content_type'],
        "file_size": upload_info['file_size'],
        "uploaded_chunks": uploaded_chunks,
        "total_chunks": total_chunks,
        "progress": (uploaded_chunks / total_chunks) * 100,
        "is_complete": uploaded_chunks == total_chunks,
        "created_at": upload_info['created_at']
    }
