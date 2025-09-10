from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..db import SessionLocal
from ..models import Artifact

router = APIRouter()

class ArtifactCreate(BaseModel):
    id: str
    document_id: str
    kind: str
    page: int
    engine: str
    payload: Dict[str, Any]
    status: str = "pending"

class ArtifactUpdate(BaseModel):
    payload: Dict[str, Any]
    status: str = "reviewed"

class ArtifactOut(BaseModel):
    id: str
    document_id: str
    kind: str
    page: int
    engine: str
    payload: Dict[str, Any]
    status: str

@router.patch("/v1/artifacts/{artifact_id}", response_model=ArtifactOut)
def update_artifact(artifact_id: str, payload: ArtifactUpdate):
    """Update an artifact's payload and status."""
    db: Session = SessionLocal()
    try:
        artifact = db.query(Artifact).filter(Artifact.id == artifact_id).first()
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        
        # Update fields
        artifact.payload = payload.payload
        artifact.status = payload.status
        
        db.commit()
        db.refresh(artifact)
        
        return {
            "id": artifact.id,
            "document_id": artifact.document_id,
            "kind": artifact.kind,
            "page": artifact.page,
            "engine": artifact.engine,
            "payload": artifact.payload,
            "status": artifact.status
        }
    
    finally:
        db.close()

@router.post("/v1/artifacts", response_model=ArtifactOut, status_code=201)
def create_artifact(payload: ArtifactCreate):
    """Create a new artifact."""
    db: Session = SessionLocal()
    try:
        artifact = Artifact(
            id=payload.id,
            document_id=payload.document_id,
            kind=payload.kind,
            page=payload.page,
            engine=payload.engine,
            payload=payload.payload,
            status=payload.status
        )
        
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        
        return {
            "id": artifact.id,
            "document_id": artifact.document_id,
            "kind": artifact.kind,
            "page": artifact.page,
            "engine": artifact.engine,
            "payload": artifact.payload,
            "status": artifact.status
        }
    
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Artifact already exists")
    
    finally:
        db.close()