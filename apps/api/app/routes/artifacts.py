import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from ..db import SessionLocal
from ..models import Artifact

router = APIRouter()

class ArtifactCreate(BaseModel):
    id: str
    document_id: str
    kind: str
    page: int
    engine: str
    payload: dict
    status: str = "pending"

class ArtifactUpdate(BaseModel):
    payload: Optional[dict] = None
    status: Optional[str] = None

class ArtifactOut(BaseModel):
    id: str
    document_id: str
    kind: str
    page: int
    engine: str
    payload: dict
    status: str
    created_at: str
    updated_at: str

@router.post("/v1/artifacts", response_model=ArtifactOut, status_code=201)
def create_artifact(artifact: ArtifactCreate):
    """Create a new artifact"""
    db: Session = SessionLocal()
    try:
        new_artifact = Artifact(
            id=artifact.id,
            document_id=artifact.document_id,
            kind=artifact.kind,
            page=artifact.page,
            engine=artifact.engine,
            payload=artifact.payload,
            status=artifact.status
        )
        db.add(new_artifact)
        db.commit()
        db.refresh(new_artifact)
        
        return {
            "id": new_artifact.id,
            "document_id": new_artifact.document_id,
            "kind": new_artifact.kind,
            "page": new_artifact.page,
            "engine": new_artifact.engine,
            "payload": new_artifact.payload,
            "status": new_artifact.status,
            "created_at": new_artifact.created_at.isoformat(),
            "updated_at": new_artifact.updated_at.isoformat()
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create artifact: {str(e)}")
    finally:
        db.close()

@router.patch("/v1/artifacts/{artifact_id}", response_model=ArtifactOut)
def update_artifact(artifact_id: str, update: ArtifactUpdate):
    """Update an artifact's payload and/or status"""
    db: Session = SessionLocal()
    try:
        artifact = db.query(Artifact).filter(Artifact.id == artifact_id).first()
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        
        if update.payload is not None:
            artifact.payload = update.payload
        if update.status is not None:
            artifact.status = update.status
        
        db.commit()
        db.refresh(artifact)
        
        return {
            "id": artifact.id,
            "document_id": artifact.document_id,
            "kind": artifact.kind,
            "page": artifact.page,
            "engine": artifact.engine,
            "payload": artifact.payload,
            "status": artifact.status,
            "created_at": artifact.created_at.isoformat(),
            "updated_at": artifact.updated_at.isoformat()
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update artifact: {str(e)}")
    finally:
        db.close()