import json
import logging
import uuid
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any, TypeVar, Generic, Union
from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import func

from .models import Document, ProcessingEvent, ProcessingStatus, EventType, Page, Artifact
from .aws import s3_client, CircuitBreakerError
from .db import db_manager

logger = logging.getLogger(__name__)

T = TypeVar('T')

class ServiceErrorType(Enum):
    """Types of service errors"""
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    ALREADY_EXISTS = "already_exists"
    DATABASE_ERROR = "database_error"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    PERMISSION_DENIED = "permission_denied"
    PROCESSING_ERROR = "processing_error"
    UNKNOWN_ERROR = "unknown_error"

@dataclass
class ServiceError:
    """Structured error information"""
    type: ServiceErrorType
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': self.type.value,
            'message': self.message,
            'details': self.details,
            'timestamp': self.timestamp.isoformat()
        }

@dataclass
class ServiceResult(Generic[T]):
    """Result wrapper for service operations"""
    success: bool
    data: Optional[T] = None
    error: Optional[ServiceError] = None
    metadata: Optional[Dict[str, Any]] = None
    
    @classmethod
    def ok(cls, data: T, metadata: Optional[Dict[str, Any]] = None) -> 'ServiceResult[T]':
        """Create successful result"""
        return cls(success=True, data=data, metadata=metadata)
    
    @classmethod
    def fail(cls, error: ServiceError, metadata: Optional[Dict[str, Any]] = None) -> 'ServiceResult[T]':
        """Create failed result"""
        return cls(success=False, error=error, metadata=metadata)
    
    def unwrap(self) -> T:
        """Get data or raise exception"""
        if not self.success:
            raise ValueError(f"Service error: {self.error.message}")
        return self.data
    
    def map(self, func: callable) -> 'ServiceResult':
        """Map function over successful result"""
        if self.success:
            try:
                return ServiceResult.ok(func(self.data), self.metadata)
            except Exception as e:
                return ServiceResult.fail(
                    ServiceError(ServiceErrorType.PROCESSING_ERROR, str(e))
                )
        return self

class BaseService:
    """Base service class with common functionality"""
    
    @staticmethod
    def log_event(
        session: Session,
        document_id: str,
        event_type: EventType,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ProcessingEvent:
        """Log a processing event"""
        event = ProcessingEvent(
            document_id=document_id,
            event_type=event_type,
            message=message,
            event_metadata=json.dumps(metadata) if metadata else None
        )
        session.add(event)
        return event
    
    @staticmethod
    def handle_database_error(e: Exception, operation: str) -> ServiceError:
        """Convert database exceptions to service errors"""
        if isinstance(e, IntegrityError):
            return ServiceError(
                ServiceErrorType.ALREADY_EXISTS,
                f"{operation} failed due to constraint violation",
                {'error': str(e)}
            )
        elif isinstance(e, SQLAlchemyError):
            return ServiceError(
                ServiceErrorType.DATABASE_ERROR,
                f"{operation} failed due to database error",
                {'error': str(e)}
            )
        else:
            return ServiceError(
                ServiceErrorType.UNKNOWN_ERROR,
                f"{operation} failed: {str(e)}",
                {'error': str(e)}
            )

class DocumentService(BaseService):
    """Enhanced document service with error handling and retry logic"""
    
    @staticmethod
    def create_document(
        s3_key: str,
        original_filename: str,
        content_type: str,
        file_size: int,
        sha256_hash: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ServiceResult[Document]:
        """Create a new document with transaction management"""
        
        def _create(session: Session) -> Document:
            # Check if document already exists
            existing = session.query(Document).filter(
                Document.s3_key == s3_key
            ).first()
            
            if existing:
                raise IntegrityError(
                    "Document already exists",
                    None,
                    None
                )
            
            # Create document
            doc = Document(
                id=str(uuid.uuid4()),
                s3_key=s3_key,
                original_filename=original_filename,
                content_type=content_type,
                file_size=file_size,
                sha256_hash=sha256_hash,
                processing_status=ProcessingStatus.UPLOADED,
                metadata=json.dumps(metadata) if metadata else None
            )
            session.add(doc)
            
            # Log creation event
            BaseService.log_event(
                session,
                doc.id,
                EventType.DOCUMENT_UPLOADED,
                f"Document uploaded: {original_filename}",
                {
                    "file_size": file_size,
                    "content_type": content_type,
                    "sha256_hash": sha256_hash
                }
            )
            
            session.commit()
            logger.info(f"Document created: {doc.id}")
            return doc
        
        try:
            doc = db_manager.execute_with_retry(_create)
            return ServiceResult.ok(doc, {'created_at': datetime.utcnow()})
        except Exception as e:
            logger.error(f"Document creation failed: {str(e)}")
            error = BaseService.handle_database_error(e, "Document creation")
            return ServiceResult.fail(error)
    
    @staticmethod
    def get_document(doc_id: str) -> ServiceResult[Document]:
        """Get document by ID"""
        
        def _get(session: Session) -> Optional[Document]:
            return session.query(Document).filter(Document.id == doc_id).first()
        
        try:
            doc = db_manager.execute_with_retry(_get)
            if not doc:
                return ServiceResult.fail(
                    ServiceError(
                        ServiceErrorType.NOT_FOUND,
                        f"Document not found: {doc_id}"
                    )
                )
            return ServiceResult.ok(doc)
        except Exception as e:
            logger.error(f"Failed to get document {doc_id}: {str(e)}")
            error = BaseService.handle_database_error(e, "Document retrieval")
            return ServiceResult.fail(error)
    
    @staticmethod
    def list_documents(
        limit: int = 10,
        offset: int = 0,
        status_filter: Optional[ProcessingStatus] = None
    ) -> ServiceResult[List[Document]]:
        """List documents with pagination"""
        
        def _list(session: Session) -> tuple[List[Document], int]:
            query = session.query(Document)
            
            if status_filter:
                query = query.filter(Document.processing_status == status_filter)
            
            total = query.count()
            docs = query.order_by(Document.created_at.desc()) \
                       .limit(limit) \
                       .offset(offset) \
                       .all()
            
            return docs, total
        
        try:
            docs, total = db_manager.execute_with_retry(_list)
            return ServiceResult.ok(
                docs,
                {'total': total, 'limit': limit, 'offset': offset}
            )
        except Exception as e:
            logger.error(f"Failed to list documents: {str(e)}")
            error = BaseService.handle_database_error(e, "Document listing")
            return ServiceResult.fail(error)
    
    @staticmethod
    def update_processing_status(
        doc_id: str,
        status: ProcessingStatus,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ServiceResult[Document]:
        """Update document processing status with audit trail"""
        
        def _update(session: Session) -> Document:
            doc = session.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                raise ValueError(f"Document not found: {doc_id}")
            
            old_status = doc.processing_status
            doc.processing_status = status
            doc.updated_at = datetime.utcnow()
            
            if error_message:
                doc.error_message = error_message
            
            # Determine event type
            event_type = EventType.PROCESSING_STARTED
            if status == ProcessingStatus.COMPLETED:
                event_type = EventType.PROCESSING_COMPLETED
            elif status == ProcessingStatus.FAILED:
                event_type = EventType.PROCESSING_FAILED
            
            # Log status change
            event_metadata = {
                'old_status': old_status.value,
                'new_status': status.value
            }
            if error_message:
                event_metadata['error_message'] = error_message
            if metadata:
                event_metadata.update(metadata)
            
            BaseService.log_event(
                session,
                doc_id,
                event_type,
                f"Status changed from {old_status.value} to {status.value}",
                event_metadata
            )
            
            session.commit()
            logger.info(f"Document {doc_id} status updated to {status.value}")
            return doc
        
        try:
            doc = db_manager.execute_with_retry(_update)
            return ServiceResult.ok(doc)
        except ValueError as e:
            return ServiceResult.fail(
                ServiceError(ServiceErrorType.NOT_FOUND, str(e))
            )
        except Exception as e:
            logger.error(f"Failed to update document status: {str(e)}")
            error = BaseService.handle_database_error(e, "Status update")
            return ServiceResult.fail(error)
    
    @staticmethod
    async def download_document_content(doc_id: str) -> ServiceResult[bytes]:
        """Download document content from S3 with circuit breaker"""
        
        # Get document first
        doc_result = DocumentService.get_document(doc_id)
        if not doc_result.success:
            return ServiceResult.fail(doc_result.error)
        
        doc = doc_result.data
        
        try:
            content = await s3_client.download_file(doc.s3_key)
            
            # Log download event
            def _log_download(session: Session):
                BaseService.log_event(
                    session,
                    doc_id,
                    EventType.DOCUMENT_DOWNLOADED,
                    f"Document downloaded: {doc.original_filename}",
                    {'file_size': len(content)}
                )
                session.commit()
            
            db_manager.execute_with_retry(_log_download)
            
            return ServiceResult.ok(
                content,
                {'filename': doc.original_filename, 'size': len(content)}
            )
            
        except CircuitBreakerError as e:
            logger.error(f"S3 circuit breaker open: {str(e)}")
            return ServiceResult.fail(
                ServiceError(
                    ServiceErrorType.EXTERNAL_SERVICE_ERROR,
                    "Storage service temporarily unavailable",
                    {'retry_after': 60}
                )
            )
        except Exception as e:
            logger.error(f"Failed to download document {doc_id}: {str(e)}")
            return ServiceResult.fail(
                ServiceError(
                    ServiceErrorType.EXTERNAL_SERVICE_ERROR,
                    f"Failed to download document: {str(e)}"
                )
            )
    
    @staticmethod
    async def get_document_metadata(doc_id: str) -> ServiceResult[Dict[str, Any]]:
        """Get document metadata including S3 info"""
        
        # Get document from database
        doc_result = DocumentService.get_document(doc_id)
        if not doc_result.success:
            return ServiceResult.fail(doc_result.error)
        
        doc = doc_result.data
        
        # Get S3 metadata
        try:
            s3_metadata = await s3_client.get_file_metadata(doc.s3_key)
            
            metadata = {
                'document': {
                    'id': doc.id,
                    'original_filename': doc.original_filename,
                    'content_type': doc.content_type,
                    'file_size': doc.file_size,
                    'sha256_hash': doc.sha256_hash,
                    'processing_status': doc.processing_status.value,
                    'created_at': doc.created_at.isoformat(),
                    'updated_at': doc.updated_at.isoformat()
                },
                's3': s3_metadata,
                'health': {
                    'file_exists': True,
                    'size_match': s3_metadata['size'] == doc.file_size
                }
            }
            
            return ServiceResult.ok(metadata)
            
        except Exception as e:
            logger.error(f"Failed to get metadata for document {doc_id}: {str(e)}")
            return ServiceResult.fail(
                ServiceError(
                    ServiceErrorType.EXTERNAL_SERVICE_ERROR,
                    f"Failed to retrieve metadata: {str(e)}"
                )
            )
    
    @staticmethod
    def get_processing_events(
        doc_id: str,
        limit: int = 50
    ) -> ServiceResult[List[ProcessingEvent]]:
        """Get processing events for a document"""
        
        def _get_events(session: Session) -> List[ProcessingEvent]:
            return session.query(ProcessingEvent) \
                         .filter(ProcessingEvent.document_id == doc_id) \
                         .order_by(ProcessingEvent.created_at.desc()) \
                         .limit(limit) \
                         .all()
        
        try:
            events = db_manager.execute_with_retry(_get_events)
            return ServiceResult.ok(events, {'count': len(events)})
        except Exception as e:
            logger.error(f"Failed to get events for document {doc_id}: {str(e)}")
            error = BaseService.handle_database_error(e, "Event retrieval")
            return ServiceResult.fail(error)
    
    @staticmethod
    async def delete_document(doc_id: str) -> ServiceResult[bool]:
        """Delete document and its S3 file"""
        
        # Get document first
        doc_result = DocumentService.get_document(doc_id)
        if not doc_result.success:
            return ServiceResult.fail(doc_result.error)
        
        doc = doc_result.data
        
        # Delete from S3 first
        try:
            await s3_client.delete_file(doc.s3_key)
        except Exception as e:
            logger.error(f"Failed to delete S3 file for document {doc_id}: {str(e)}")
            # Continue with database deletion even if S3 fails
        
        # Delete from database
        def _delete(session: Session) -> bool:
            # Delete related records first
            session.query(ProcessingEvent).filter(
                ProcessingEvent.document_id == doc_id
            ).delete()
            
            session.query(Page).filter(
                Page.document_id == doc_id
            ).delete()
            
            session.query(Artifact).filter(
                Artifact.document_id == doc_id
            ).delete()
            
            # Delete document
            session.query(Document).filter(
                Document.id == doc_id
            ).delete()
            
            session.commit()
            return True
        
        try:
            db_manager.execute_with_retry(_delete)
            logger.info(f"Document {doc_id} deleted successfully")
            return ServiceResult.ok(True)
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {str(e)}")
            error = BaseService.handle_database_error(e, "Document deletion")
            return ServiceResult.fail(error)

# Export for backward compatibility
__all__ = [
    'DocumentService',
    'ServiceResult',
    'ServiceError',
    'ServiceErrorType',
    'BaseService'
]