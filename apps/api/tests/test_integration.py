import pytest
import tempfile
import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db import Base, SessionLocal
from app.models import Document, ProcessingStatus
from app.services import DocumentService

# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture
def client():
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Override the database dependency
    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[SessionLocal] = override_get_db
    
    with TestClient(app) as c:
        yield c
    
    # Clean up
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()

@pytest.fixture
def sample_document():
    return {
        "s3_key": "test/sample.pdf",
        "original_filename": "sample.pdf",
        "content_type": "application/pdf",
        "file_size": 1024,
        "sha256_hash": "abc123"
    }

def test_health_check(client):
    """Test basic health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_presign_upload_validation(client):
    """Test presigned URL generation with validation"""
    # Valid request
    valid_request = {
        "filename": "test.pdf",
        "content_type": "application/pdf",
        "file_size": 1024
    }
    response = client.post("/v1/uploads/presign", json=valid_request)
    assert response.status_code == 200
    data = response.json()
    assert "key" in data
    assert "url" in data
    assert data["key"].startswith("raw/")
    assert data["key"].endswith("-test.pdf")

def test_presign_upload_invalid_file_type(client):
    """Test presigned URL generation with invalid file type"""
    invalid_request = {
        "filename": "test.txt",
        "content_type": "text/plain",
        "file_size": 1024
    }
    response = client.post("/v1/uploads/presign", json=invalid_request)
    assert response.status_code == 422

def test_presign_upload_file_too_large(client):
    """Test presigned URL generation with file too large"""
    large_request = {
        "filename": "test.pdf", 
        "content_type": "application/pdf",
        "file_size": 200 * 1024 * 1024  # 200MB, larger than 100MB limit
    }
    response = client.post("/v1/uploads/presign", json=large_request)
    assert response.status_code == 422

def test_presign_upload_invalid_filename(client):
    """Test presigned URL generation with invalid filename"""
    invalid_request = {
        "filename": "../../../etc/passwd",
        "content_type": "application/pdf",
        "file_size": 1024
    }
    response = client.post("/v1/uploads/presign", json=invalid_request)
    assert response.status_code == 422

def test_create_document(client, sample_document):
    """Test document creation"""
    response = client.post("/v1/documents", json=sample_document)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["s3_key"] == sample_document["s3_key"]
    assert data["original_filename"] == sample_document["original_filename"]
    assert data["processing_status"] == "uploaded"

def test_create_duplicate_document(client, sample_document):
    """Test creating duplicate document fails"""
    # Create first document
    response = client.post("/v1/documents", json=sample_document)
    assert response.status_code == 201

    # Try to create duplicate
    response = client.post("/v1/documents", json=sample_document)
    assert response.status_code == 409

def test_get_document(client, sample_document):
    """Test retrieving a document"""
    # Create document
    create_response = client.post("/v1/documents", json=sample_document)
    assert create_response.status_code == 201
    doc_id = create_response.json()["id"]

    # Get document
    response = client.get(f"/v1/documents/{doc_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == doc_id
    assert data["s3_key"] == sample_document["s3_key"]

def test_get_nonexistent_document(client):
    """Test retrieving a non-existent document"""
    response = client.get("/v1/documents/nonexistent-id")
    assert response.status_code == 404

def test_full_upload_flow(client):
    """Test complete upload flow: presign -> create document"""
    # 1. Request presigned URL
    presign_response = client.post("/v1/uploads/presign", json={
        "filename": "test.pdf",
        "content_type": "application/pdf",
        "file_size": 1024
    })
    assert presign_response.status_code == 200
    presign_data = presign_response.json()
    
    # 2. Register document (simulating successful S3 upload)
    register_response = client.post("/v1/documents", json={
        "s3_key": presign_data["key"],
        "original_filename": "test.pdf",
        "content_type": "application/pdf",
        "file_size": 1024
    })
    assert register_response.status_code == 201
    doc_data = register_response.json()
    assert "id" in doc_data
    assert doc_data["processing_status"] == "uploaded"

def test_document_service_audit_trail():
    """Test that document service creates proper audit trail"""
    # This test uses the service directly to test audit functionality
    doc = DocumentService.create_document(
        s3_key="test/audit.pdf",
        original_filename="audit.pdf", 
        content_type="application/pdf",
        file_size=2048
    )
    
    assert doc.id is not None
    assert doc.processing_status == ProcessingStatus.UPLOADED
    
    # Test status update creates audit event
    DocumentService.update_processing_status(
        doc.id, 
        ProcessingStatus.PROCESSING
    )
    
    # Verify status was updated
    updated_doc = DocumentService.get_document(doc.id)
    assert updated_doc.processing_status == ProcessingStatus.PROCESSING

def test_document_service_error_handling():
    """Test document service error handling"""
    # Test getting non-existent document
    doc = DocumentService.get_document("non-existent-id")
    assert doc is None
    
    # Test updating non-existent document
    with pytest.raises(ValueError, match="Document not found"):
        DocumentService.update_processing_status("non-existent-id", ProcessingStatus.COMPLETED)

def test_document_processing_state_machine(client, sample_document):
    """Test document status transitions"""
    # Create document
    doc_response = client.post("/v1/documents", json=sample_document)
    doc_id = doc_response.json()["id"]
    
    # Verify initial state
    get_response = client.get(f"/v1/documents/{doc_id}")
    assert get_response.json()["processing_status"] == "uploaded"
    
    # Test state transitions through service layer
    DocumentService.update_processing_status(doc_id, ProcessingStatus.PROCESSING)
    get_response = client.get(f"/v1/documents/{doc_id}")
    assert get_response.json()["processing_status"] == "processing"
    
    DocumentService.update_processing_status(doc_id, ProcessingStatus.COMPLETED)
    get_response = client.get(f"/v1/documents/{doc_id}")
    assert get_response.json()["processing_status"] == "completed"

def test_error_response_format(client):
    """Test that error responses follow consistent format"""
    # Test 404 error
    response = client.get("/v1/documents/nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    
    # Test 422 validation error
    response = client.post("/v1/uploads/presign", json={
        "filename": "test.txt",
        "content_type": "text/plain",  # Invalid content type
        "file_size": 1024
    })
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data

@pytest.mark.parametrize("content_type,expected_status", [
    ("application/pdf", 200),
    ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", 200),
    ("text/plain", 422),
    ("image/jpeg", 422),
    ("application/json", 422),
])
def test_content_type_validation(client, content_type, expected_status):
    """Test content type validation for different file types"""
    request_data = {
        "filename": "test.file",
        "content_type": content_type,
        "file_size": 1024
    }
    response = client.post("/v1/uploads/presign", json=request_data)
    assert response.status_code == expected_status

@pytest.mark.parametrize("file_size,expected_status", [
    (1024, 200),  # 1KB - valid
    (50 * 1024 * 1024, 200),  # 50MB - valid
    (100 * 1024 * 1024, 200),  # 100MB - at limit
    (101 * 1024 * 1024, 422),  # 101MB - over limit
    (200 * 1024 * 1024, 422),  # 200MB - way over limit
])
def test_file_size_validation(client, file_size, expected_status):
    """Test file size validation"""
    request_data = {
        "filename": "test.pdf",
        "content_type": "application/pdf",
        "file_size": file_size
    }
    response = client.post("/v1/uploads/presign", json=request_data)
    assert response.status_code == expected_status