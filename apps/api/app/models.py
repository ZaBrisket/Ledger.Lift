from sqlalchemy import Column, String, DateTime, func, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    s3_key: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())

    pages: Mapped[list["Page"]] = relationship("Page", back_populates="document", cascade="all, delete-orphan")

class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String, ForeignKey("documents.id"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    document: Mapped["Document"] = relationship("Document", back_populates="pages")
