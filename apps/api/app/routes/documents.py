import uuid
import io
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List, Optional

from ..db import SessionLocal
from ..models import Document, Artifact
from ..aws import get_s3_client
from ..settings import settings
from ..exporter.xlsx import build_workbook
from fastapi.responses import StreamingResponse

router = APIRouter()

class DocumentCreate(BaseModel):
    s3_key: str
    original_filename: str

class DocumentOut(BaseModel):
    id: str
    s3_key: str
    original_filename: str

class PreviewsResponse(BaseModel):
    images: List[str]

class ArtifactOut(BaseModel):
    id: str
    kind: str
    page: int
    engine: str
    payload: dict
    status: str
    created_at: str
    updated_at: str

class PaginatedDocuments(BaseModel):
    items: List[DocumentOut]
    total: int
    limit: int
    cursor: Optional[str] = None
    has_more: bool = False

@router.post("/v1/documents", response_model=DocumentOut, status_code=201)
def create_document(payload: DocumentCreate):
    doc_id = str(uuid.uuid4())
    db: Session = SessionLocal()
    try:
        doc = Document(id=doc_id, s3_key=payload.s3_key, original_filename=payload.original_filename)
        db.add(doc)
        db.commit()
        return {"id": doc_id, "s3_key": doc.s3_key, "original_filename": doc.original_filename}
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Document already exists")
    finally:
        db.close()

@router.get("/v1/documents", response_model=PaginatedDocuments)
def list_documents(
    limit: int = 20,
    cursor: Optional[str] = None
):
    """List documents with pagination"""
    if limit > 100:
        limit = 100  # Cap at 100 items per page
    
    db: Session = SessionLocal()
    try:
        # Build query
        query = db.query(Document)
        
        # Apply cursor-based pagination
        if cursor:
            try:
                # Simple cursor: timestamp-based
                cursor_timestamp = float(cursor)
                query = query.filter(Document.created_at < cursor_timestamp)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid cursor format")
        
        # Order by created_at descending
        query = query.order_by(Document.created_at.desc())
        
        # Get total count
        total = query.count()
        
        # Apply limit and get one extra to check if there are more
        items = query.limit(limit + 1).all()
        
        # Check if there are more items
        has_more = len(items) > limit
        if has_more:
            items = items[:limit]  # Remove the extra item
        
        # Convert to response format
        document_items = [
            {
                "id": doc.id,
                "s3_key": doc.s3_key,
                "original_filename": doc.original_filename
            }
            for doc in items
        ]
        
        # Generate next cursor
        next_cursor = None
        if has_more and items:
            next_cursor = str(items[-1].created_at.timestamp())
        
        return {
            "items": document_items,
            "total": total,
            "limit": limit,
            "cursor": next_cursor,
            "has_more": has_more
        }
    finally:
        db.close()

@router.get("/v1/documents/{doc_id}/previews", response_model=PreviewsResponse)
def get_document_previews(doc_id: str):
    """Get signed URLs for document preview images"""
    s3 = get_s3_client()
    
    # List objects in the previews folder for this document
    try:
        response = s3.list_objects_v2(
            Bucket=settings.s3_bucket,
            Prefix=f"previews/{doc_id}/"
        )
        
        if 'Contents' not in response:
            return {"images": []}
        
        # Generate presigned URLs for each image
        images = []
        for obj in response['Contents']:
            if obj['Key'].endswith('.png'):
                url = s3.generate_presigned_url(
                    ClientMethod="get_object",
                    Params={"Bucket": settings.s3_bucket, "Key": obj['Key']},
                    ExpiresIn=settings.presign_ttl_seconds
                )
                images.append(url)
        
        return {"images": images}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get previews: {str(e)}")

@router.get("/v1/documents/{doc_id}/artifacts", response_model=List[ArtifactOut])
def get_document_artifacts(
    doc_id: str,
    limit: int = 50,
    cursor: Optional[str] = None
):
    """Get artifacts for a document with pagination"""
    if limit > 100:
        limit = 100  # Cap at 100 items per page
    
    db: Session = SessionLocal()
    try:
        # Build query
        query = db.query(Artifact).filter(Artifact.document_id == doc_id)
        
        # Apply cursor-based pagination
        if cursor:
            try:
                # Simple cursor: timestamp-based
                cursor_timestamp = float(cursor)
                query = query.filter(Artifact.created_at < cursor_timestamp)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid cursor format")
        
        # Order by created_at descending
        query = query.order_by(Artifact.created_at.desc())
        
        # Apply limit
        artifacts = query.limit(limit).all()
        
        return [
            {
                "id": artifact.id,
                "kind": artifact.kind,
                "page": artifact.page,
                "engine": artifact.engine,
                "payload": artifact.payload,
                "status": artifact.status,
                "created_at": artifact.created_at.isoformat(),
                "updated_at": artifact.updated_at.isoformat()
            }
            for artifact in artifacts
        ]
    finally:
        db.close()

@router.get("/v1/documents/{doc_id}/export.xlsx")
def export_document_to_excel(doc_id: str):
    """Export document artifacts to Excel workbook"""
    db: Session = SessionLocal()
    try:
        # Get document info
        document = db.query(Document).filter(Document.id == doc_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get all artifacts
        artifacts = db.query(Artifact).filter(Artifact.document_id == doc_id).all()
        
        # Convert to dict format for exporter
        artifacts_data = [
            {
                "id": artifact.id,
                "kind": artifact.kind,
                "page": artifact.page,
                "engine": artifact.engine,
                "payload": artifact.payload,
                "status": artifact.status,
                "created_at": artifact.created_at.isoformat(),
                "updated_at": artifact.updated_at.isoformat()
            }
            for artifact in artifacts
        ]
        
        # Document info
        document_info = {
            "original_filename": document.original_filename,
            "created_at": document.created_at.isoformat()
        }
        
        # Build workbook
        workbook_bytes = build_workbook(doc_id, artifacts_data, document_info)
        
        # Return as streaming response
        return StreamingResponse(
            io.BytesIO(workbook_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=document_{doc_id}_export.xlsx"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export document: {str(e)}")
    finally:
        db.close()

@router.delete("/v1/documents/{doc_id}")
def delete_document(doc_id: str):
    """Delete a document and all associated S3 objects"""
    db: Session = SessionLocal()
    try:
        # Get document info
        document = db.query(Document).filter(Document.id == doc_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        s3 = get_s3_client()
        deleted_objects = 0
        
        # Delete raw document
        try:
            s3.delete_object(Bucket=settings.s3_bucket, Key=document.s3_key)
            deleted_objects += 1
        except Exception as e:
            print(f"Warning: Failed to delete raw document {document.s3_key}: {e}")
        
        # Delete preview images
        try:
            response = s3.list_objects_v2(
                Bucket=settings.s3_bucket,
                Prefix=f"previews/{doc_id}/"
            )
            
            if 'Contents' in response:
                objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
                if objects_to_delete:
                    s3.delete_objects(
                        Bucket=settings.s3_bucket,
                        Delete={'Objects': objects_to_delete}
                    )
                    deleted_objects += len(objects_to_delete)
        except Exception as e:
            print(f"Warning: Failed to delete preview images: {e}")
        
        # Delete database records (cascade will handle artifacts)
        db.delete(document)
        db.commit()
        
        return {
            "message": f"Document deleted successfully",
            "deleted_objects": deleted_objects
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")
    finally:
        db.close()
