from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel
from ..services import DocumentService, ServiceErrorType
from ..models import ProcessingStatus

router = APIRouter()

class DocumentCreate(BaseModel):
    s3_key: str
    original_filename: str
    content_type: str = "application/pdf"
    file_size: int
    sha256_hash: Optional[str] = None
    metadata: Optional[dict] = None

class DocumentOut(BaseModel):
    id: str
    s3_key: str
    original_filename: str
    content_type: str
    file_size: int
    processing_status: str
    sha256_hash: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str

class DocumentListResponse(BaseModel):
    documents: List[DocumentOut]
    total: int
    limit: int
    offset: int

class ProcessingEventOut(BaseModel):
    id: str
    document_id: str
    event_type: str
    message: str
    event_metadata: Optional[str] = None
    created_at: str

@router.post("/v1/documents", response_model=DocumentOut, status_code=201)
async def create_document(payload: DocumentCreate):
    """Create a new document record"""
    result = DocumentService.create_document(
        s3_key=payload.s3_key,
        original_filename=payload.original_filename,
        content_type=payload.content_type,
        file_size=payload.file_size,
        sha256_hash=payload.sha256_hash,
        metadata=payload.metadata
    )
    
    if not result.success:
        if result.error.type == ServiceErrorType.ALREADY_EXISTS:
            raise HTTPException(status_code=409, detail=result.error.to_dict())
        elif result.error.type == ServiceErrorType.VALIDATION_ERROR:
            raise HTTPException(status_code=400, detail=result.error.to_dict())
        else:
            raise HTTPException(status_code=500, detail=result.error.to_dict())
    
    doc = result.data
    return DocumentOut(
        id=doc.id,
        s3_key=doc.s3_key,
        original_filename=doc.original_filename,
        content_type=doc.content_type,
        file_size=doc.file_size,
        processing_status=doc.processing_status.value,
        sha256_hash=doc.sha256_hash,
        error_message=doc.error_message,
        created_at=doc.created_at.isoformat(),
        updated_at=doc.updated_at.isoformat()
    )

@router.get("/v1/documents", response_model=DocumentListResponse)
async def list_documents(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Filter by processing status")
):
    """List documents with pagination"""
    status_filter = None
    if status:
        try:
            status_filter = ProcessingStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid status: {status}. Valid values: {[s.value for s in ProcessingStatus]}"
            )
    
    result = DocumentService.list_documents(limit, offset, status_filter)
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error.to_dict())
    
    return DocumentListResponse(
        documents=[
            DocumentOut(
                id=doc.id,
                s3_key=doc.s3_key,
                original_filename=doc.original_filename,
                content_type=doc.content_type,
                file_size=doc.file_size,
                processing_status=doc.processing_status.value,
                sha256_hash=doc.sha256_hash,
                error_message=doc.error_message,
                created_at=doc.created_at.isoformat(),
                updated_at=doc.updated_at.isoformat()
            ) for doc in result.data
        ],
        total=result.metadata['total'],
        limit=result.metadata['limit'],
        offset=result.metadata['offset']
    )

@router.get("/v1/documents/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: str):
    """Get a specific document by ID"""
    result = DocumentService.get_document(doc_id)
    
    if not result.success:
        if result.error.type == ServiceErrorType.NOT_FOUND:
            raise HTTPException(status_code=404, detail=result.error.to_dict())
        else:
            raise HTTPException(status_code=500, detail=result.error.to_dict())
    
    doc = result.data
    return DocumentOut(
        id=doc.id,
        s3_key=doc.s3_key,
        original_filename=doc.original_filename,
        content_type=doc.content_type,
        file_size=doc.file_size,
        processing_status=doc.processing_status.value,
        sha256_hash=doc.sha256_hash,
        error_message=doc.error_message,
        created_at=doc.created_at.isoformat(),
        updated_at=doc.updated_at.isoformat()
    )

@router.patch("/v1/documents/{doc_id}/status")
async def update_document_status(
    doc_id: str,
    status: str,
    error_message: Optional[str] = None
):
    """Update document processing status"""
    try:
        status_enum = ProcessingStatus(status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status: {status}. Valid values: {[s.value for s in ProcessingStatus]}"
        )
    
    result = DocumentService.update_processing_status(doc_id, status_enum, error_message)
    
    if not result.success:
        if result.error.type == ServiceErrorType.NOT_FOUND:
            raise HTTPException(status_code=404, detail=result.error.to_dict())
        else:
            raise HTTPException(status_code=500, detail=result.error.to_dict())
    
    return {"message": "Status updated successfully"}

@router.get("/v1/documents/{doc_id}/download")
async def download_document(doc_id: str):
    """Download document content"""
    # Get document metadata first
    doc_result = DocumentService.get_document(doc_id)
    if not doc_result.success:
        if doc_result.error.type == ServiceErrorType.NOT_FOUND:
            raise HTTPException(status_code=404, detail=doc_result.error.to_dict())
        else:
            raise HTTPException(status_code=500, detail=doc_result.error.to_dict())
    
    doc = doc_result.data
    
    # Download content
    content_result = await DocumentService.download_document_content(doc_id)
    
    if not content_result.success:
        raise HTTPException(status_code=500, detail=content_result.error.to_dict())
    
    return Response(
        content=content_result.data,
        media_type=doc.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{doc.original_filename}"'
        }
    )

@router.get("/v1/documents/{doc_id}/metadata")
async def get_document_metadata(doc_id: str):
    """Get comprehensive document metadata including S3 info"""
    result = await DocumentService.get_document_metadata(doc_id)
    
    if not result.success:
        if result.error.type == ServiceErrorType.NOT_FOUND:
            raise HTTPException(status_code=404, detail=result.error.to_dict())
        else:
            raise HTTPException(status_code=500, detail=result.error.to_dict())
    
    return result.data

@router.get("/v1/documents/{doc_id}/events", response_model=List[ProcessingEventOut])
async def get_document_events(doc_id: str, limit: int = Query(50, ge=1, le=100)):
    """Get processing events for a document"""
    result = DocumentService.get_processing_events(doc_id, limit)
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error.to_dict())
    
    return [
        ProcessingEventOut(
            id=str(event.id),
            document_id=event.document_id,
            event_type=event.event_type.value,
            message=event.message,
            event_metadata=event.event_metadata,
            created_at=event.created_at.isoformat()
        ) for event in result.data
    ]

@router.delete("/v1/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document and its associated data"""
    result = await DocumentService.delete_document(doc_id)
    
    if not result.success:
        if result.error.type == ServiceErrorType.NOT_FOUND:
            raise HTTPException(status_code=404, detail=result.error.to_dict())
        else:
            raise HTTPException(status_code=500, detail=result.error.to_dict())
    
    return {"message": "Document deleted successfully"}