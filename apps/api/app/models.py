from sqlalchemy import Column, String, DateTime, func, Integer, ForeignKey, Enum, BigInteger, Text, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from enum import Enum as PyEnum
from .db import Base

class ProcessingStatus(PyEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

class EventType(PyEnum):
    DOCUMENT_UPLOADED = "document_uploaded"
    PROCESSING_STARTED = "processing_started"
    PROCESSING_COMPLETED = "processing_completed"
    PROCESSING_FAILED = "processing_failed"
    EXTRACTION_COMPLETED = "extraction_completed"
    MANUAL_REVIEW_STARTED = "manual_review_started"

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    s3_key: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    sha256_raw: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    sha256_canonical: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    processing_status: Mapped[ProcessingStatus] = mapped_column(Enum(ProcessingStatus), default=ProcessingStatus.UPLOADED)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

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
