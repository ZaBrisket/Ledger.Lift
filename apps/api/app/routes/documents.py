import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Document

router = APIRouter()

class DocumentCreate(BaseModel):
    s3_key: str
    original_filename: str

class DocumentOut(BaseModel):
    id: str
    s3_key: str
    original_filename: str

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
