import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Document, Artifact
from ..aws import get_s3_client, generate_presigned_url
from ..settings import settings
from ..exporter.xlsx import build_workbook

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

class ArtifactsResponse(BaseModel):
    artifacts: List[ArtifactOut]
    cursor: Optional[str] = None
    has_more: bool = False

class DocumentsResponse(BaseModel):
    documents: List[DocumentOut]
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

@router.get("/v1/documents", response_model=DocumentsResponse)
def list_documents(
    limit: int = Query(default=50, le=100, description="Number of documents to return"),
    cursor: Optional[str] = Query(default=None, description="Opaque cursor for pagination")
):
    """List documents with pagination."""
    db: Session = SessionLocal()
    try:
        query = db.query(Document).order_by(Document.created_at.desc())
        
        # Apply cursor-based pagination
        if cursor:
            try:
                # Simple cursor implementation using created_at timestamp
                import base64
                cursor_time = base64.b64decode(cursor.encode()).decode()
                query = query.filter(Document.created_at < cursor_time)
            except Exception:
                # Invalid cursor, ignore
                pass
        
        # Get one extra to check if there are more results
        documents = query.limit(limit + 1).all()
        
        has_more = len(documents) > limit
        if has_more:
            documents = documents[:limit]
        
        # Generate next cursor
        next_cursor = None
        if has_more and documents:
            import base64
            cursor_time = documents[-1].created_at.isoformat()
            next_cursor = base64.b64encode(cursor_time.encode()).decode()
        
        document_list = [
            {
                "id": doc.id,
                "s3_key": doc.s3_key,
                "original_filename": doc.original_filename
            }
            for doc in documents
        ]
        
        return {
            "documents": document_list,
            "cursor": next_cursor,
            "has_more": has_more
        }
    
    finally:
        db.close()

@router.get("/v1/documents/{doc_id}/previews", response_model=PreviewsResponse)
def get_document_previews(doc_id: str):
    """Get presigned URLs for document preview images."""
    db: Session = SessionLocal()
    try:
        # Check if document exists
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # List preview objects in S3
        s3_client = get_s3_client()
        
        try:
            # List objects with the preview prefix
            response = s3_client.list_objects_v2(
                Bucket=settings.s3_bucket,
                Prefix=f"previews/{doc_id}/"
            )
            
            preview_urls = []
            if 'Contents' in response:
                # Sort by key to ensure page order
                objects = sorted(response['Contents'], key=lambda x: x['Key'])
                
                for obj in objects:
                    # Generate presigned GET URL for each preview
                    params = {'Bucket': settings.s3_bucket, 'Key': obj['Key']}
                    presigned_url = generate_presigned_url(s3_client, 'get_object', params)
                    preview_urls.append(presigned_url)
            
            return {"images": preview_urls}
            
        except Exception as e:
            # Return empty array if S3 listing fails (previews might not exist yet)
            return {"images": []}
    
    finally:
        db.close()

@router.get("/v1/documents/{doc_id}/artifacts", response_model=ArtifactsResponse)
def get_document_artifacts(
    doc_id: str,
    limit: int = Query(default=50, le=100, description="Number of artifacts to return"),
    cursor: Optional[str] = Query(default=None, description="Opaque cursor for pagination")
):
    """Get artifacts for a document with pagination."""
    db: Session = SessionLocal()
    try:
        # Check if document exists
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        query = db.query(Artifact).filter(Artifact.document_id == doc_id).order_by(Artifact.created_at.desc())
        
        # Apply cursor-based pagination
        if cursor:
            try:
                import base64
                cursor_time = base64.b64decode(cursor.encode()).decode()
                query = query.filter(Artifact.created_at < cursor_time)
            except Exception:
                # Invalid cursor, ignore
                pass
        
        # Get one extra to check if there are more results
        artifacts = query.limit(limit + 1).all()
        
        has_more = len(artifacts) > limit
        if has_more:
            artifacts = artifacts[:limit]
        
        # Generate next cursor
        next_cursor = None
        if has_more and artifacts:
            import base64
            cursor_time = artifacts[-1].created_at.isoformat()
            next_cursor = base64.b64encode(cursor_time.encode()).decode()
        
        artifact_list = [
            {
                "id": artifact.id,
                "kind": artifact.kind,
                "page": artifact.page,
                "engine": artifact.engine,
                "payload": artifact.payload,
                "status": artifact.status
            }
            for artifact in artifacts
        ]
        
        return {
            "artifacts": artifact_list,
            "cursor": next_cursor,
            "has_more": has_more
        }
    
    finally:
        db.close()

@router.get("/v1/documents/{doc_id}/export.xlsx")
def export_document_excel(doc_id: str):
    """Export document artifacts as Excel workbook."""
    try:
        # Build workbook
        excel_bytes = build_workbook(doc_id)
        
        # Return as downloadable file
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=ledger_lift_{doc_id}.xlsx"
            }
        )
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

@router.delete("/v1/documents/{doc_id}")
def delete_document(doc_id: str):
    """Delete document and all associated S3 objects."""
    db: Session = SessionLocal()
    try:
        # Check if document exists
        document = db.query(Document).filter(Document.id == doc_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        s3_client = get_s3_client()
        
        # Delete S3 objects
        objects_deleted = 0
        errors = []
        
        # Delete raw document
        try:
            s3_client.delete_object(Bucket=settings.s3_bucket, Key=document.s3_key)
            objects_deleted += 1
        except Exception as e:
            errors.append(f"Failed to delete raw document: {str(e)}")
        
        # Delete preview images
        try:
            response = s3_client.list_objects_v2(
                Bucket=settings.s3_bucket,
                Prefix=f"previews/{doc_id}/"
            )
            
            if 'Contents' in response:
                for obj in response['Contents']:
                    try:
                        s3_client.delete_object(Bucket=settings.s3_bucket, Key=obj['Key'])
                        objects_deleted += 1
                    except Exception as e:
                        errors.append(f"Failed to delete {obj['Key']}: {str(e)}")
        except Exception as e:
            errors.append(f"Failed to list preview objects: {str(e)}")
        
        # Delete database records (cascading will handle artifacts and pages)
        db.delete(document)
        db.commit()
        
        return {
            "message": "Document deleted successfully",
            "objects_deleted": objects_deleted,
            "errors": errors if errors else None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")
    finally:
        db.close()
