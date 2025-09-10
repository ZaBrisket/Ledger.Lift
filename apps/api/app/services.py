import json
import logging
import uuid
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .models import Document, ProcessingEvent, ProcessingStatus, EventType
from .aws import download_file
from .db import SessionLocal

logger = logging.getLogger(__name__)

class DocumentService:
    @staticmethod
    def create_document(s3_key: str, original_filename: str, content_type: str, 
                       file_size: int, sha256_hash: Optional[str] = None) -> Document:
        db = SessionLocal()
        try:
            doc = Document(
                id=str(uuid.uuid4()),
                s3_key=s3_key,
                original_filename=original_filename,
                content_type=content_type,
                file_size=file_size,
                sha256_hash=sha256_hash,
                processing_status=ProcessingStatus.UPLOADED
            )
            db.add(doc)
            
            # Log creation event
            event = ProcessingEvent(
                document_id=doc.id,
                event_type=EventType.DOCUMENT_UPLOADED,
                message=f"Document uploaded: {original_filename}",
                event_metadata=json.dumps({"file_size": file_size, "content_type": content_type})
            )
            db.add(event)
            
            db.commit()
            logger.info(f"Document created: {doc.id}")
            return doc
        except IntegrityError as e:
            db.rollback()
            logger.error(f"Document creation failed: {e}")
            raise ValueError("Document already exists")
        finally:
            db.close()

    @staticmethod
    def get_document(doc_id: str) -> Optional[Document]:
        db = SessionLocal()
        try:
            return db.query(Document).filter(Document.id == doc_id).first()
        finally:
            db.close()

    @staticmethod
    def update_processing_status(doc_id: str, status: ProcessingStatus, 
                               error_message: Optional[str] = None) -> None:
        db = SessionLocal()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                raise ValueError(f"Document not found: {doc_id}")
            
            doc.processing_status = status
            if error_message:
                doc.error_message = error_message
            
            # Log status change
            event = ProcessingEvent(
                document_id=doc_id,
                event_type=EventType.PROCESSING_STARTED if status == ProcessingStatus.PROCESSING 
                          else EventType.PROCESSING_COMPLETED if status == ProcessingStatus.COMPLETED
                          else EventType.PROCESSING_FAILED,
                message=f"Status changed to {status.value}",
                event_metadata=json.dumps({"error_message": error_message} if error_message else {})
            )
            db.add(event)
            db.commit()
            logger.info(f"Document {doc_id} status updated to {status.value}")
        finally:
            db.close()

    @staticmethod
    def download_document_content(doc_id: str) -> bytes:
        doc = DocumentService.get_document(doc_id)
        if not doc:
            raise ValueError(f"Document not found: {doc_id}")
        
        try:
            return download_file(doc.s3_key)
        except Exception as e:
            logger.error(f"Failed to download document {doc_id}: {e}")
            raise