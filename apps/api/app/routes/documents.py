from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..services import DocumentService

router = APIRouter()

class DocumentCreate(BaseModel):
    s3_key: str
    original_filename: str
    content_type: str
    file_size: int
    sha256_hash: str = None

class DocumentOut(BaseModel):
    id: str
    s3_key: str
    original_filename: str
    content_type: str
    file_size: int
    processing_status: str

@router.post("/v1/documents", response_model=DocumentOut, status_code=201)
def create_document(payload: DocumentCreate):
    try:
        doc = DocumentService.create_document(
            s3_key=payload.s3_key,
            original_filename=payload.original_filename,
            content_type=payload.content_type,
            file_size=payload.file_size,
            sha256_hash=payload.sha256_hash
        )
        return {
            "id": doc.id,
            "s3_key": doc.s3_key,
            "original_filename": doc.original_filename,
            "content_type": doc.content_type,
            "file_size": doc.file_size,
            "processing_status": doc.processing_status.value
        }
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create document: {str(e)}")

@router.get("/v1/documents/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: str):
    doc = DocumentService.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {
        "id": doc.id,
        "s3_key": doc.s3_key,
        "original_filename": doc.original_filename,
        "content_type": doc.content_type,
        "file_size": doc.file_size,
        "processing_status": doc.processing_status.value
    }
