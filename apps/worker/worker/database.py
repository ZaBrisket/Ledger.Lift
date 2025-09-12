import os
from sqlalchemy import create_engine, Column, String, DateTime, func, Integer, ForeignKey, Enum, BigInteger, Text, Float
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column, relationship
from .models import ProcessingStatus, EventType

class Base(DeclarativeBase):
    pass

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    s3_key: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    processing_status: Mapped[ProcessingStatus] = mapped_column(Enum(ProcessingStatus), default=ProcessingStatus.UPLOADED)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    pages: Mapped[list["Page"]] = relationship("Page", back_populates="document", cascade="all, delete-orphan")
    events: Mapped[list["ProcessingEvent"]] = relationship("ProcessingEvent", back_populates="document", cascade="all, delete-orphan")
    artifacts: Mapped[list["Artifact"]] = relationship("Artifact", back_populates="document", cascade="all, delete-orphan")

class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String, ForeignKey("documents.id"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    preview_s3_key: Mapped[str] = mapped_column(String, nullable=True)
    width: Mapped[int] = mapped_column(Integer, nullable=True)
    height: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document"] = relationship("Document", back_populates="pages")

class ProcessingEvent(Base):
    __tablename__ = "processing_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String, ForeignKey("documents.id"), nullable=False)
    event_type: Mapped[EventType] = mapped_column(Enum(EventType), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=True)
    event_metadata: Mapped[str] = mapped_column(Text, nullable=True)  # JSON string
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document"] = relationship("Document", back_populates="events")

class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String, ForeignKey("documents.id"), nullable=False)
    page_id: Mapped[int] = mapped_column(Integer, ForeignKey("pages.id"), nullable=True)
    artifact_type: Mapped[str] = mapped_column(String, nullable=False)  # "table", "figure", "text"
    s3_key: Mapped[str] = mapped_column(String, nullable=True)
    extraction_engine: Mapped[str] = mapped_column(String, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=True)
    bbox_x: Mapped[int] = mapped_column(Integer, nullable=True)
    bbox_y: Mapped[int] = mapped_column(Integer, nullable=True)
    bbox_width: Mapped[int] = mapped_column(Integer, nullable=True)
    bbox_height: Mapped[int] = mapped_column(Integer, nullable=True)
    data: Mapped[str] = mapped_column(Text, nullable=True)  # JSON string
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document"] = relationship("Document", back_populates="artifacts")

class WorkerDatabase:
    def __init__(self):
        db_url = os.getenv('DATABASE_URL', 'postgresql+psycopg://postgres:postgres@localhost:5432/ledgerlift')
        self.engine = create_engine(db_url, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False)

    def get_document(self, doc_id: str):
        with self.SessionLocal() as session:
            return session.query(Document).filter(Document.id == doc_id).first()

    def update_document_status(self, doc_id: str, status: ProcessingStatus, error_message: str = None):
        with self.SessionLocal() as session:
            doc = session.query(Document).filter(Document.id == doc_id).first()
            if doc:
                doc.processing_status = status
                if error_message:
                    doc.error_message = error_message
                session.commit()

    def create_page(self, document_id: str, page_number: int, preview_s3_key: str = None, 
                   width: int = None, height: int = None):
        with self.SessionLocal() as session:
            page = Page(
                document_id=document_id,
                page_number=page_number,
                preview_s3_key=preview_s3_key,
                width=width,
                height=height
            )
            session.add(page)
            session.commit()
            return page

    def log_event(self, document_id: str, event_type: EventType, message: str, event_metadata: str = None):
        with self.SessionLocal() as session:
            event = ProcessingEvent(
                document_id=document_id,
                event_type=event_type,
                message=message,
                event_metadata=event_metadata
            )
            session.add(event)
            session.commit()
    
    def create_artifact(self, document_id: str, artifact_type: str, extraction_engine: str = None,
                       confidence_score: float = None, data: str = None, page_id: int = None,
                       s3_key: str = None, bbox_x: int = None, bbox_y: int = None,
                       bbox_width: int = None, bbox_height: int = None):
        with self.SessionLocal() as session:
            artifact = Artifact(
                document_id=document_id,
                page_id=page_id,
                artifact_type=artifact_type,
                s3_key=s3_key,
                extraction_engine=extraction_engine,
                confidence_score=confidence_score,
                bbox_x=bbox_x,
                bbox_y=bbox_y,
                bbox_width=bbox_width,
                bbox_height=bbox_height,
                data=data
            )
            session.add(artifact)
            session.commit()
            return artifact