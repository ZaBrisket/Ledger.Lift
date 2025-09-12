import logging
import time
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Header, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, validator
from ..services import DocumentService
from ..models import ProcessingStatus
from io import BytesIO
import os

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])

class DocumentCreate(BaseModel):
    s3_key: str
    original_filename: str
    content_type: str
    file_size: int
    sha256_hash: Optional[str] = None
    
    @validator('s3_key')
    def validate_s3_key(cls, v):
        if not v or not v.strip():
            raise ValueError('S3 key cannot be empty')
        if len(v) > 1024:
            raise ValueError('S3 key too long (max 1024 characters)')
        if '..' in v:
            raise ValueError('S3 key cannot contain path traversal')
        return v.strip()
    
    @validator('original_filename')
    def validate_filename(cls, v):
        if not v or not v.strip():
            raise ValueError('Filename cannot be empty')
        if len(v) > 255:
            raise ValueError('Filename too long (max 255 characters)')
        return v.strip()
    
    @validator('content_type')
    def validate_content_type(cls, v):
        if not v or not v.strip():
            raise ValueError('Content type cannot be empty')
        allowed = {
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        }
        if v not in allowed:
            raise ValueError(f'Unsupported content type: {v}')
        return v
    
    @validator('file_size')
    def validate_file_size(cls, v):
        if v <= 0:
            raise ValueError('File size must be positive')
        if v > 100 * 1024 * 1024:  # 100MB limit
            raise ValueError('File size too large (max 100MB)')
        return v
    
    @validator('sha256_hash')
    def validate_sha256_hash(cls, v):
        if v is not None:
            v = v.strip()
            if v:
                # Normalize to lowercase for canonical form
                v = v.lower()
                if len(v) != 64 or not all(c in '0123456789abcdef' for c in v):
                    raise ValueError('Invalid SHA256 hash format - must be 64 lowercase hex characters')
                return v
            return None
        return v

class DocumentOut(BaseModel):
    id: str
    s3_key: str
    original_filename: str
    content_type: str
    file_size: int
    processing_status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class DocumentListResponse(BaseModel):
    documents: List[DocumentOut]
    total: int
    page: int
    per_page: int
    
class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[dict] = None

@router.post("/v1/documents", response_model=DocumentOut, status_code=201)
def create_document(
    payload: DocumentCreate,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    """Create a new document with comprehensive validation and error handling."""
    start_time = time.time()
    
    logger.info(f"Document creation started", extra={
        "s3_key": payload.s3_key,
        "filename": payload.original_filename,
        "content_type": payload.content_type,
        "file_size": payload.file_size,
        "idempotency_key": idempotency_key
    })
    
    try:
        # Use the service layer which already has proper error handling
        result = DocumentService.create_document(
            s3_key=payload.s3_key,
            original_filename=payload.original_filename,
            content_type=payload.content_type,
            file_size=payload.file_size,
            sha256_hash=payload.sha256_hash
        )
        
        if not result.success:
            processing_time = time.time() - start_time
            logger.warning(f"Document creation failed: {result.error}", extra={
                "error_code": result.error_code,
                "s3_key": payload.s3_key,
                "processing_time_ms": round(processing_time * 1000, 2)
            })
            
            # Map service errors to HTTP status codes
            status_code = 500
            if result.error_code == "DUPLICATE_DOCUMENT":
                status_code = 409
            elif result.error_code == "INTEGRITY_ERROR":
                status_code = 409
            elif result.error_code == "DATABASE_ERROR":
                status_code = 503
                
            raise HTTPException(
                status_code=status_code,
                detail={
                    "error": result.error_code or "UNKNOWN_ERROR",
                    "message": result.error,
                    "details": result.metadata
                }
            )
        
        doc = result.data
        processing_time = time.time() - start_time
        
        logger.info(f"Document created successfully: {doc.id}", extra={
            "document_id": doc.id,
            "s3_key": doc.s3_key,
            "processing_time_ms": round(processing_time * 1000, 2)
        })
        
        return {
            "id": doc.id,
            "s3_key": doc.s3_key,
            "original_filename": doc.original_filename,
            "content_type": doc.content_type,
            "file_size": doc.file_size,
            "processing_status": doc.processing_status.value,
            "created_at": doc.created_at.isoformat() if hasattr(doc, 'created_at') and doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if hasattr(doc, 'updated_at') and doc.updated_at else None
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Unexpected error creating document: {e}", extra={
            "error_type": type(e).__name__,
            "s3_key": payload.s3_key,
            "processing_time_ms": round(processing_time * 1000, 2)
        })
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Internal server error"
            }
        )

@router.get("/v1/documents", response_model=DocumentListResponse)
def list_documents(
    status: Optional[str] = Query(None, description="Filter by processing status"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page (max 100)")
):
    """List documents with pagination and optional status filtering."""
    start_time = time.time()
    
    logger.debug(f"Listing documents: page={page}, per_page={per_page}, status={status}")
    
    try:
        # Validate status parameter
        if status:
            try:
                status_enum = ProcessingStatus(status.lower())
            except ValueError:
                valid_statuses = [s.value for s in ProcessingStatus]
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "INVALID_STATUS",
                        "message": f"Invalid status. Valid options: {', '.join(valid_statuses)}"
                    }
                )
        else:
            status_enum = None
        
        # Get documents from service
        if status_enum:
            result = DocumentService.get_documents_by_status(status_enum, limit=per_page)
        else:
            # For now, get uploaded documents as default
            result = DocumentService.get_documents_by_status(ProcessingStatus.UPLOADED, limit=per_page)
        
        if not result.success:
            processing_time = time.time() - start_time
            logger.warning(f"Document listing failed: {result.error}", extra={
                "error_code": result.error_code,
                "processing_time_ms": round(processing_time * 1000, 2)
            })
            
            status_code = 500
            if result.error_code == "DATABASE_ERROR":
                status_code = 503
                
            raise HTTPException(
                status_code=status_code,
                detail={
                    "error": result.error_code or "UNKNOWN_ERROR",
                    "message": result.error,
                    "details": result.metadata
                }
            )
        
        documents = result.data
        processing_time = time.time() - start_time
        
        logger.debug(f"Documents listed: {len(documents)} items in {processing_time:.3f}s")
        
        # Convert documents to response format
        document_list = []
        for doc in documents:
            document_list.append({
                "id": doc.id,
                "s3_key": doc.s3_key,
                "original_filename": doc.original_filename,
                "content_type": doc.content_type,
                "file_size": doc.file_size,
                "processing_status": doc.processing_status.value,
                "created_at": doc.created_at.isoformat() if hasattr(doc, 'created_at') and doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() if hasattr(doc, 'updated_at') and doc.updated_at else None
            })
        
        return {
            "documents": document_list,
            "total": len(document_list),  # In production, get actual total count
            "page": page,
            "per_page": per_page
        }
        
    except HTTPException:
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Unexpected error listing documents: {e}", extra={
            "error_type": type(e).__name__,
            "processing_time_ms": round(processing_time * 1000, 2)
        })
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Internal server error"
            }
        )

@router.get("/v1/documents/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: str):
    """Get document by ID with comprehensive error handling."""
    start_time = time.time()
    
    # Input validation
    if not doc_id or not doc_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_INPUT",
                "message": "Document ID cannot be empty"
            }
        )
    
    doc_id = doc_id.strip()
    if len(doc_id) > 100:  # Reasonable limit for UUID
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_INPUT",
                "message": "Document ID too long"
            }
        )
    
    logger.debug(f"Getting document: {doc_id}")
    
    try:
        result = DocumentService.get_document(doc_id)
        
        if not result.success:
            processing_time = time.time() - start_time
            logger.warning(f"Document retrieval failed: {result.error}", extra={
                "document_id": doc_id,
                "error_code": result.error_code,
                "processing_time_ms": round(processing_time * 1000, 2)
            })
            
            status_code = 500
            if result.error_code == "NOT_FOUND":
                status_code = 404
            elif result.error_code == "DATABASE_ERROR":
                status_code = 503
                
            raise HTTPException(
                status_code=status_code,
                detail={
                    "error": result.error_code or "UNKNOWN_ERROR",
                    "message": result.error,
                    "details": result.metadata
                }
            )
        
        doc = result.data
        processing_time = time.time() - start_time
        
        logger.debug(f"Document retrieved: {doc_id} in {processing_time:.3f}s")
        
        return {
            "id": doc.id,
            "s3_key": doc.s3_key,
            "original_filename": doc.original_filename,
            "content_type": doc.content_type,
            "file_size": doc.file_size,
            "processing_status": doc.processing_status.value,
            "created_at": doc.created_at.isoformat() if hasattr(doc, 'created_at') and doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if hasattr(doc, 'updated_at') and doc.updated_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Unexpected error retrieving document {doc_id}: {e}", extra={
            "document_id": doc_id,
            "error_type": type(e).__name__,
            "processing_time_ms": round(processing_time * 1000, 2)
        })
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Internal server error"
            }
        )

@router.get("/v1/documents/{doc_id}/export/excel")
def export_document_excel(doc_id: str):
    """Export document as Excel file with extracted table data."""
    start_time = time.time()
    
    # Input validation
    if not doc_id or not doc_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_INPUT",
                "message": "Document ID cannot be empty"
            }
        )
    
    doc_id = doc_id.strip()
    if len(doc_id) > 100:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_INPUT",
                "message": "Document ID too long"
            }
        )
    
    logger.info(f"Excel export requested for document: {doc_id}")
    
    try:
        result = DocumentService.generate_excel_output(doc_id)
        
        if not result.success:
            processing_time = time.time() - start_time
            logger.warning(f"Excel export failed: {result.error}", extra={
                "document_id": doc_id,
                "error_code": result.error_code,
                "processing_time_ms": round(processing_time * 1000, 2)
            })
            
            status_code = 500
            if result.error_code == "NOT_FOUND":
                status_code = 404
            elif result.error_code == "NO_ARTIFACTS":
                status_code = 404
            elif result.error_code == "ARTIFACTS_ERROR":
                status_code = 503
            elif result.error_code == "EXCEL_ERROR":
                status_code = 500
                
            raise HTTPException(
                status_code=status_code,
                detail={
                    "error": result.error_code or "UNKNOWN_ERROR",
                    "message": result.error,
                    "details": result.metadata
                }
            )
        
        excel_bytes = result.data
        processing_time = time.time() - start_time
        
        logger.info(f"Excel export completed: {doc_id} ({len(excel_bytes)} bytes) in {processing_time:.3f}s")
        
        # Create streaming response
        def generate():
            yield excel_bytes
        
        return StreamingResponse(
            generate(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=document_{doc_id}_extracted_tables.xlsx",
                "Content-Length": str(len(excel_bytes))
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Unexpected error exporting Excel for {doc_id}: {e}", extra={
            "document_id": doc_id,
            "error_type": type(e).__name__,
            "processing_time_ms": round(processing_time * 1000, 2)
        })
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "Internal server error"
            }
        )
