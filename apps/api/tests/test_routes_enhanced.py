"""
Enhanced test suite for API routes with comprehensive error handling and edge case coverage.
Follows reliability testing patterns with deterministic behavior.
"""
import pytest
import json
import uuid
import time
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db import Base, get_db_session
from app.models import Document, ProcessingStatus
from app.services import DocumentService, ServiceResult


# Test database setup with deterministic behavior
TEST_DATABASE_URL = "sqlite:///./test_enhanced.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def client():
    """Test client with isolated database."""
    Base.metadata.create_all(bind=engine)
    
    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db_session] = override_get_db
    
    with TestClient(app) as c:
        yield c
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


@pytest.fixture
def mock_s3_healthy():
    """Mock S3 manager in healthy state."""
    with patch('app.routes.uploads.s3_manager') as mock_s3:
        mock_s3.health_check.return_value = {'status': 'healthy'}
        mock_s3.generate_presigned_url.return_value = 'https://example.com/presigned-url'
        yield mock_s3


@pytest.fixture
def mock_s3_unhealthy():
    """Mock S3 manager in unhealthy state."""
    with patch('app.routes.uploads.s3_manager') as mock_s3:
        mock_s3.health_check.return_value = {
            'status': 'unhealthy', 
            'error': 'Connection timeout'
        }
        yield mock_s3


@pytest.fixture
def fixed_time():
    """Fixed time for deterministic testing."""
    fixed_timestamp = 1609459200.0  # 2021-01-01 00:00:00 UTC
    with patch('time.time', return_value=fixed_timestamp):
        yield fixed_timestamp


@pytest.fixture
def fixed_uuid():
    """Fixed UUID for deterministic testing."""
    fixed_id = "12345678-1234-5678-9abc-123456789012"
    with patch('uuid.uuid4', return_value=Mock(spec=uuid.UUID, __str__=lambda x: fixed_id)):
        yield fixed_id


class TestPresignUpload:
    """Test presigned URL generation with comprehensive error handling."""

    def test_presign_valid_request(self, client, mock_s3_healthy, fixed_time, fixed_uuid):
        """Test successful presigned URL generation."""
        request_data = {
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        }
        
        response = client.post("/v1/uploads/presign", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "key" in data
        assert "url" in data
        assert "expires_in" in data
        assert "upload_id" in data
        assert data["key"].startswith("raw/")
        assert data["key"].endswith("-test.pdf")
        assert data["upload_id"] == fixed_uuid
        
        # Verify S3 manager was called correctly
        mock_s3_healthy.health_check.assert_called_once()
        mock_s3_healthy.generate_presigned_url.assert_called_once()

    def test_presign_with_idempotency_key(self, client, mock_s3_healthy):
        """Test presigned URL with idempotency key."""
        request_data = {
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        }
        headers = {"Idempotency-Key": "test-key-123"}
        
        response = client.post("/v1/uploads/presign", json=request_data, headers=headers)
        
        assert response.status_code == 200

    def test_presign_s3_unhealthy(self, client, mock_s3_unhealthy):
        """Test presigned URL when S3 is unhealthy."""
        request_data = {
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        }
        
        response = client.post("/v1/uploads/presign", json=request_data)
        
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["error"] == "SERVICE_UNAVAILABLE"
        assert "temporarily unavailable" in data["detail"]["message"]

    def test_presign_s3_error(self, client, mock_s3_healthy):
        """Test presigned URL when S3 operation fails."""
        mock_s3_healthy.generate_presigned_url.side_effect = Exception("S3 connection failed")
        
        request_data = {
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        }
        
        response = client.post("/v1/uploads/presign", json=request_data)
        
        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["error"] == "STORAGE_ERROR"

    @pytest.mark.parametrize("filename,expected_error", [
        ("", "Filename cannot be empty"),
        ("a" * 256, "Filename too long"),
        ("../../../etc/passwd", "path traversal characters"),
        ("file\x00.pdf", "control characters"),
        (".hidden", "cannot start or end with period"),
        ("file.", "cannot start or end with period"),
    ])
    def test_presign_invalid_filename(self, client, mock_s3_healthy, filename, expected_error):
        """Test filename validation edge cases."""
        request_data = {
            "filename": filename,
            "content_type": "application/pdf",
            "file_size": 1024
        }
        
        response = client.post("/v1/uploads/presign", json=request_data)
        
        assert response.status_code == 422
        error_detail = response.json()["detail"]
        assert any(expected_error in str(error) for error in error_detail)

    @pytest.mark.parametrize("content_type,expected_status", [
        ("application/pdf", 200),
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", 200),
        ("", 422),
        ("text/plain", 422),
        ("image/jpeg", 422),
        ("application/json", 422),
    ])
    def test_presign_content_type_validation(self, client, mock_s3_healthy, content_type, expected_status):
        """Test content type validation."""
        request_data = {
            "filename": "test.file",
            "content_type": content_type,
            "file_size": 1024
        }
        
        response = client.post("/v1/uploads/presign", json=request_data)
        assert response.status_code == expected_status

    @pytest.mark.parametrize("file_size,expected_status", [
        (1, 200),  # Minimum valid size
        (1024, 200),  # Normal size
        (100 * 1024 * 1024, 200),  # At limit
        (0, 422),  # Invalid: zero
        (-1, 422),  # Invalid: negative
        (101 * 1024 * 1024, 422),  # Invalid: over limit
    ])
    def test_presign_file_size_validation(self, client, mock_s3_healthy, file_size, expected_status):
        """Test file size validation."""
        request_data = {
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": file_size
        }
        
        response = client.post("/v1/uploads/presign", json=request_data)
        assert response.status_code == expected_status

    def test_presign_empty_filename_after_sanitization(self, client, mock_s3_healthy):
        """Test filename that becomes empty after sanitization."""
        request_data = {
            "filename": "!@#$%^&*()",  # All special chars, will be sanitized to empty
            "content_type": "application/pdf",
            "file_size": 1024
        }
        
        response = client.post("/v1/uploads/presign", json=request_data)
        
        # Should still succeed, using fallback filename
        assert response.status_code == 200
        data = response.json()
        assert "unnamed_file" in data["key"]


class TestDocumentOperations:
    """Test document CRUD operations with comprehensive error handling."""

    def test_create_document_success(self, client, fixed_time):
        """Test successful document creation."""
        with patch.object(DocumentService, 'create_document') as mock_create:
            mock_doc = Mock()
            mock_doc.id = "doc-123"
            mock_doc.s3_key = "raw/test.pdf"
            mock_doc.original_filename = "test.pdf"
            mock_doc.content_type = "application/pdf"
            mock_doc.file_size = 1024
            mock_doc.processing_status = ProcessingStatus.UPLOADED
            mock_doc.created_at = None
            mock_doc.updated_at = None
            
            mock_create.return_value = ServiceResult.success_result(mock_doc)
            
            request_data = {
                "s3_key": "raw/test.pdf",
                "original_filename": "test.pdf",
                "content_type": "application/pdf",
                "file_size": 1024
            }
            
            response = client.post("/v1/documents", json=request_data)
            
            assert response.status_code == 201
            data = response.json()
            assert data["id"] == "doc-123"
            assert data["processing_status"] == "uploaded"

    def test_create_document_duplicate(self, client):
        """Test duplicate document creation."""
        with patch.object(DocumentService, 'create_document') as mock_create:
            mock_create.return_value = ServiceResult.error_result(
                "Document already exists",
                "DUPLICATE_DOCUMENT",
                {"existing_id": "existing-123"}
            )
            
            request_data = {
                "s3_key": "raw/test.pdf",
                "original_filename": "test.pdf",
                "content_type": "application/pdf",
                "file_size": 1024
            }
            
            response = client.post("/v1/documents", json=request_data)
            
            assert response.status_code == 409
            data = response.json()
            assert data["detail"]["error"] == "DUPLICATE_DOCUMENT"
            assert "existing_id" in data["detail"]["details"]

    def test_create_document_database_error(self, client):
        """Test document creation with database error."""
        with patch.object(DocumentService, 'create_document') as mock_create:
            mock_create.return_value = ServiceResult.error_result(
                "Database connection failed",
                "DATABASE_ERROR"
            )
            
            request_data = {
                "s3_key": "raw/test.pdf",
                "original_filename": "test.pdf",
                "content_type": "application/pdf",
                "file_size": 1024
            }
            
            response = client.post("/v1/documents", json=request_data)
            
            assert response.status_code == 503
            data = response.json()
            assert data["detail"]["error"] == "DATABASE_ERROR"

    @pytest.mark.parametrize("field,value,expected_error", [
        ("s3_key", "", "S3 key cannot be empty"),
        ("s3_key", "a" * 1025, "S3 key too long"),
        ("s3_key", "path/../traversal", "path traversal"),
        ("original_filename", "", "Filename cannot be empty"),
        ("original_filename", "a" * 256, "Filename too long"),
        ("content_type", "", "Content type cannot be empty"),
        ("content_type", "text/plain", "Unsupported content type"),
        ("file_size", 0, "File size must be positive"),
        ("file_size", -1, "File size must be positive"),
        ("file_size", 101 * 1024 * 1024, "File size too large"),
    ])
    def test_create_document_validation(self, client, field, value, expected_error):
        """Test document creation input validation."""
        base_data = {
            "s3_key": "raw/test.pdf",
            "original_filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        }
        base_data[field] = value
        
        response = client.post("/v1/documents", json=base_data)
        
        assert response.status_code == 422
        error_detail = response.json()["detail"]
        assert any(expected_error in str(error) for error in error_detail)

    def test_create_document_sha256_validation(self, client):
        """Test SHA256 hash validation."""
        with patch.object(DocumentService, 'create_document') as mock_create:
            mock_doc = Mock()
            mock_doc.id = "doc-123"
            mock_doc.s3_key = "raw/test.pdf"
            mock_doc.original_filename = "test.pdf"
            mock_doc.content_type = "application/pdf"
            mock_doc.file_size = 1024
            mock_doc.processing_status = ProcessingStatus.UPLOADED
            mock_doc.created_at = None
            mock_doc.updated_at = None
            
            mock_create.return_value = ServiceResult.success_result(mock_doc)
            
            # Valid SHA256 hash
            request_data = {
                "s3_key": "raw/test.pdf",
                "original_filename": "test.pdf",
                "content_type": "application/pdf",
                "file_size": 1024,
                "sha256_hash": "a" * 64  # Valid 64-char hex string
            }
            
            response = client.post("/v1/documents", json=request_data)
            assert response.status_code == 201

    def test_create_document_invalid_sha256(self, client):
        """Test invalid SHA256 hash."""
        request_data = {
            "s3_key": "raw/test.pdf",
            "original_filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024,
            "sha256_hash": "invalid-hash"  # Invalid format
        }
        
        response = client.post("/v1/documents", json=request_data)
        
        assert response.status_code == 422

    def test_get_document_success(self, client):
        """Test successful document retrieval."""
        with patch.object(DocumentService, 'get_document') as mock_get:
            mock_doc = Mock()
            mock_doc.id = "doc-123"
            mock_doc.s3_key = "raw/test.pdf"
            mock_doc.original_filename = "test.pdf"
            mock_doc.content_type = "application/pdf"
            mock_doc.file_size = 1024
            mock_doc.processing_status = ProcessingStatus.COMPLETED
            mock_doc.created_at = None
            mock_doc.updated_at = None
            
            mock_get.return_value = ServiceResult.success_result(mock_doc)
            
            response = client.get("/v1/documents/doc-123")
            
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "doc-123"
            assert data["processing_status"] == "completed"

    def test_get_document_not_found(self, client):
        """Test document not found."""
        with patch.object(DocumentService, 'get_document') as mock_get:
            mock_get.return_value = ServiceResult.error_result(
                "Document not found",
                "NOT_FOUND",
                {"document_id": "nonexistent"}
            )
            
            response = client.get("/v1/documents/nonexistent")
            
            assert response.status_code == 404
            data = response.json()
            assert data["detail"]["error"] == "NOT_FOUND"

    @pytest.mark.parametrize("doc_id,expected_status", [
        ("", 400),  # Empty ID
        ("   ", 400),  # Whitespace only
        ("a" * 101, 400),  # Too long
        ("valid-id-123", 200),  # Valid ID
    ])
    def test_get_document_id_validation(self, client, doc_id, expected_status):
        """Test document ID validation."""
        if expected_status == 200:
            with patch.object(DocumentService, 'get_document') as mock_get:
                mock_doc = Mock()
                mock_doc.id = doc_id
                mock_doc.s3_key = "raw/test.pdf"
                mock_doc.original_filename = "test.pdf"
                mock_doc.content_type = "application/pdf"
                mock_doc.file_size = 1024
                mock_doc.processing_status = ProcessingStatus.UPLOADED
                mock_doc.created_at = None
                mock_doc.updated_at = None
                
                mock_get.return_value = ServiceResult.success_result(mock_doc)
        
        response = client.get(f"/v1/documents/{doc_id}")
        assert response.status_code == expected_status

    def test_list_documents_success(self, client):
        """Test successful document listing."""
        with patch.object(DocumentService, 'get_documents_by_status') as mock_list:
            mock_docs = [Mock() for _ in range(3)]
            for i, doc in enumerate(mock_docs):
                doc.id = f"doc-{i}"
                doc.s3_key = f"raw/test{i}.pdf"
                doc.original_filename = f"test{i}.pdf"
                doc.content_type = "application/pdf"
                doc.file_size = 1024
                doc.processing_status = ProcessingStatus.UPLOADED
                doc.created_at = None
                doc.updated_at = None
            
            mock_list.return_value = ServiceResult.success_result(mock_docs)
            
            response = client.get("/v1/documents")
            
            assert response.status_code == 200
            data = response.json()
            assert len(data["documents"]) == 3
            assert data["total"] == 3
            assert data["page"] == 1
            assert data["per_page"] == 20

    def test_list_documents_with_status_filter(self, client):
        """Test document listing with status filter."""
        with patch.object(DocumentService, 'get_documents_by_status') as mock_list:
            mock_docs = []
            mock_list.return_value = ServiceResult.success_result(mock_docs)
            
            response = client.get("/v1/documents?status=completed")
            
            assert response.status_code == 200
            mock_list.assert_called_with(ProcessingStatus.COMPLETED, limit=20)

    def test_list_documents_invalid_status(self, client):
        """Test document listing with invalid status."""
        response = client.get("/v1/documents?status=invalid_status")
        
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "INVALID_STATUS"

    @pytest.mark.parametrize("page,per_page,expected_status", [
        (1, 20, 200),  # Valid
        (1, 100, 200),  # At limit
        (0, 20, 422),  # Invalid page
        (1, 0, 422),  # Invalid per_page
        (1, 101, 422),  # Over limit
    ])
    def test_list_documents_pagination_validation(self, client, page, per_page, expected_status):
        """Test pagination parameter validation."""
        if expected_status == 200:
            with patch.object(DocumentService, 'get_documents_by_status') as mock_list:
                mock_list.return_value = ServiceResult.success_result([])
        
        response = client.get(f"/v1/documents?page={page}&per_page={per_page}")
        assert response.status_code == expected_status


class TestErrorHandling:
    """Test comprehensive error handling patterns."""

    def test_service_layer_exception_handling(self, client):
        """Test that service layer exceptions are properly handled."""
        with patch.object(DocumentService, 'create_document') as mock_create:
            mock_create.side_effect = Exception("Unexpected database error")
            
            request_data = {
                "s3_key": "raw/test.pdf",
                "original_filename": "test.pdf",
                "content_type": "application/pdf",
                "file_size": 1024
            }
            
            response = client.post("/v1/documents", json=request_data)
            
            assert response.status_code == 500
            data = response.json()
            assert data["detail"]["error"] == "INTERNAL_ERROR"
            assert data["detail"]["message"] == "Internal server error"

    def test_consistent_error_response_format(self, client):
        """Test that all errors follow consistent response format."""
        # Test 400 error
        response = client.get("/v1/documents/")  # Empty ID
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "error" in data["detail"]
        assert "message" in data["detail"]
        
        # Test 422 validation error
        response = client.post("/v1/uploads/presign", json={
            "filename": "test.txt",
            "content_type": "text/plain",  # Invalid
            "file_size": 1024
        })
        assert response.status_code == 422
        assert "detail" in response.json()


class TestPerformanceAndReliability:
    """Test performance monitoring and reliability features."""

    def test_request_timing_logged(self, client, mock_s3_healthy, caplog):
        """Test that request timing is logged."""
        request_data = {
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        }
        
        response = client.post("/v1/uploads/presign", json=request_data)
        
        assert response.status_code == 200
        # Check that timing information is in logs
        assert any("processing_time_ms" in record.message for record in caplog.records)

    def test_correlation_id_logging(self, client, mock_s3_healthy, caplog, fixed_uuid):
        """Test that correlation IDs are logged for tracing."""
        request_data = {
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        }
        
        response = client.post("/v1/uploads/presign", json=request_data)
        
        assert response.status_code == 200
        # Check that request ID is in logs
        assert any(fixed_uuid in record.message for record in caplog.records)

    def test_circuit_breaker_integration(self, client, mock_s3_unhealthy):
        """Test integration with S3 circuit breaker."""
        request_data = {
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        }
        
        response = client.post("/v1/uploads/presign", json=request_data)
        
        assert response.status_code == 503
        mock_s3_unhealthy.health_check.assert_called_once()

    def test_deterministic_behavior_with_fixed_inputs(self, client, mock_s3_healthy, fixed_time, fixed_uuid):
        """Test that responses are deterministic with fixed inputs."""
        request_data = {
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        }
        
        response1 = client.post("/v1/uploads/presign", json=request_data)
        response2 = client.post("/v1/uploads/presign", json=request_data)
        
        # Both responses should be identical (except for different request IDs)
        assert response1.status_code == response2.status_code == 200
        data1 = response1.json()
        data2 = response2.json()
        
        # Key generation should be deterministic
        assert data1["upload_id"] == data2["upload_id"] == fixed_uuid


# Integration tests with real database
class TestIntegrationWithDatabase:
    """Integration tests using real database operations."""

    def test_full_document_lifecycle(self, client):
        """Test complete document lifecycle from creation to retrieval."""
        # Create document
        create_data = {
            "s3_key": "raw/lifecycle-test.pdf",
            "original_filename": "lifecycle-test.pdf",
            "content_type": "application/pdf",
            "file_size": 2048,
            "sha256_hash": "a1b2c3d4e5f6" + "0" * 58  # Valid 64-char hash
        }
        
        create_response = client.post("/v1/documents", json=create_data)
        assert create_response.status_code == 201
        
        doc_data = create_response.json()
        doc_id = doc_data["id"]
        
        # Retrieve document
        get_response = client.get(f"/v1/documents/{doc_id}")
        assert get_response.status_code == 200
        
        retrieved_doc = get_response.json()
        assert retrieved_doc["id"] == doc_id
        assert retrieved_doc["s3_key"] == create_data["s3_key"]
        assert retrieved_doc["original_filename"] == create_data["original_filename"]
        
        # List documents should include our document
        list_response = client.get("/v1/documents")
        assert list_response.status_code == 200
        
        list_data = list_response.json()
        doc_ids = [doc["id"] for doc in list_data["documents"]]
        assert doc_id in doc_ids

    def test_duplicate_detection(self, client):
        """Test that duplicate documents are properly detected."""
        create_data = {
            "s3_key": "raw/duplicate-test.pdf",
            "original_filename": "duplicate-test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        }
        
        # First creation should succeed
        response1 = client.post("/v1/documents", json=create_data)
        assert response1.status_code == 201
        
        # Second creation should fail with 409
        response2 = client.post("/v1/documents", json=create_data)
        assert response2.status_code == 409
        
        data = response2.json()
        assert data["detail"]["error"] == "DUPLICATE_DOCUMENT"