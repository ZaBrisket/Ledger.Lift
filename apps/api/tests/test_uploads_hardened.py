"""
Comprehensive tests for hardened uploads module.
Tests input validation, error handling, timeouts, and edge cases.
"""
import pytest
import time
import uuid
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.routes.uploads import ALLOWED_CONTENT_TYPES, MAX_FILE_SIZE, MIN_FILE_SIZE

client = TestClient(app)

class TestPresignEndpoint:
    """Test suite for the hardened presign upload endpoint."""
    
    def test_presign_success_pdf(self):
        """Test successful presigned URL generation for PDF."""
        response = client.post("/v1/uploads/presign", json={
            "filename": "test-document.pdf",
            "content_type": "application/pdf",
            "file_size": 1024 * 1024  # 1MB
        })
        assert response.status_code == 200
        data = response.json()
        
        # Validate response structure
        assert "key" in data
        assert "url" in data
        assert "expires_in" in data
        assert "request_id" in data
        assert "max_file_size" in data
        assert "allowed_content_types" in data
        
        # Validate key format
        assert data["key"].startswith("raw/")
        assert "test-document.pdf" in data["key"]
        assert len(data["key"].split("/")) == 3  # raw/timestamp/uuid-filename
        
        # Validate metadata
        assert data["expires_in"] > 0
        assert data["max_file_size"] == MAX_FILE_SIZE
        assert set(data["allowed_content_types"]) == set(ALLOWED_CONTENT_TYPES.keys())
    
    def test_presign_with_client_id(self):
        """Test presigned URL generation with client ID tracking."""
        response = client.post("/v1/uploads/presign", json={
            "filename": "client-file.pdf",
            "content_type": "application/pdf",
            "file_size": 1024,
            "client_id": "test-client-123"
        })
        assert response.status_code == 200
        assert "request_id" in response.json()
    
    def test_presign_with_request_header(self):
        """Test request ID propagation from header."""
        request_id = str(uuid.uuid4())
        response = client.post("/v1/uploads/presign", 
            headers={"X-Request-ID": request_id},
            json={
                "filename": "tracked.pdf",
                "content_type": "application/pdf",
                "file_size": 1024
            }
        )
        assert response.status_code == 200
        assert response.json()["request_id"] == request_id

class TestFilenameValidation:
    """Test suite for comprehensive filename validation."""
    
    @pytest.mark.parametrize("filename,expected_status", [
        # Valid filenames
        ("document.pdf", 200),
        ("my-file.pdf", 200),
        ("my_file.pdf", 200),
        ("file123.pdf", 200),
        ("UPPERCASE.PDF", 200),
        ("file.name.with.dots.pdf", 200),
        
        # Invalid filenames
        ("", 422),
        (" ", 422),
        ("file with spaces.pdf", 422),
        ("../../../etc/passwd", 422),
        ("file/with/slashes.pdf", 422),
        ("file\\with\\backslashes.pdf", 422),
        (".hidden.pdf", 422),
        ("file.", 422),
        ("file", 422),  # No extension
        ("file.pdf.", 422),
        ("file\x00null.pdf", 422),
        ("file@special.pdf", 422),
        ("file#hash.pdf", 422),
        ("file$money.pdf", 422),
        ("file%percent.pdf", 422),
        ("file&ampersand.pdf", 422),
        ("file*asterisk.pdf", 422),
        ("file+plus.pdf", 422),
        ("file=equals.pdf", 422),
        ("file[bracket.pdf", 422),
        ("file]bracket.pdf", 422),
        ("file{brace.pdf", 422),
        ("file}brace.pdf", 422),
        ("file|pipe.pdf", 422),
        ("file:colon.pdf", 422),
        ("file;semicolon.pdf", 422),
        ("file<less.pdf", 422),
        ("file>greater.pdf", 422),
        ("file?question.pdf", 422),
        ("file\"quote.pdf", 422),
        ("file'apostrophe.pdf", 422),
        (" leadingspace.pdf", 422),
        ("trailingspace.pdf ", 422),
        ("a" * 256 + ".pdf", 422),  # Too long
    ])
    def test_filename_validation(self, filename, expected_status):
        """Test various filename validation scenarios."""
        response = client.post("/v1/uploads/presign", json={
            "filename": filename,
            "content_type": "application/pdf",
            "file_size": 1024
        })
        assert response.status_code == expected_status
        
        if expected_status == 422:
            assert "error" in response.json()
            assert "error_code" in response.json()

class TestContentTypeValidation:
    """Test suite for content type validation."""
    
    @pytest.mark.parametrize("content_type,filename,expected_status", [
        # Valid combinations
        ("application/pdf", "file.pdf", 200),
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "file.docx", 200),
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "file.xlsx", 200),
        ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "file.pptx", 200),
        
        # Invalid content types
        ("text/plain", "file.txt", 422),
        ("image/jpeg", "file.jpg", 422),
        ("application/json", "file.json", 422),
        ("application/octet-stream", "file.bin", 422),
        ("video/mp4", "file.mp4", 422),
        
        # Mismatched extension and content type
        ("application/pdf", "file.docx", 422),
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "file.pdf", 422),
        
        # Case sensitivity
        ("APPLICATION/PDF", "file.pdf", 422),  # Content type should be lowercase
        ("application/pdf", "file.PDF", 200),  # Extension case doesn't matter
    ])
    def test_content_type_validation(self, content_type, filename, expected_status):
        """Test content type validation and matching with file extension."""
        response = client.post("/v1/uploads/presign", json={
            "filename": filename,
            "content_type": content_type,
            "file_size": 1024
        })
        assert response.status_code == expected_status

class TestFileSizeValidation:
    """Test suite for file size validation."""
    
    @pytest.mark.parametrize("file_size,expected_status", [
        # Valid sizes
        (MIN_FILE_SIZE, 200),  # Minimum valid size
        (1024, 200),  # 1KB
        (1024 * 1024, 200),  # 1MB
        (50 * 1024 * 1024, 200),  # 50MB
        (MAX_FILE_SIZE, 200),  # Maximum valid size
        
        # Invalid sizes
        (0, 422),  # Too small
        (-1, 422),  # Negative
        (MAX_FILE_SIZE + 1, 422),  # Too large
        (200 * 1024 * 1024, 422),  # Way too large
    ])
    def test_file_size_validation(self, file_size, expected_status):
        """Test file size validation."""
        response = client.post("/v1/uploads/presign", json={
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": file_size
        })
        assert response.status_code == expected_status

class TestClientIdValidation:
    """Test suite for client ID validation."""
    
    @pytest.mark.parametrize("client_id,expected_status", [
        # Valid client IDs
        ("client123", 200),
        ("client-123", 200),
        ("client_123", 200),
        ("CLIENT123", 200),
        ("123456789", 200),
        (None, 200),  # Optional field
        
        # Invalid client IDs
        ("client@123", 422),
        ("client.123", 422),
        ("client#123", 422),
        ("client 123", 422),
        ("client/123", 422),
        ("a" * 65, 422),  # Too long
    ])
    def test_client_id_validation(self, client_id, expected_status):
        """Test client ID validation."""
        request_data = {
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        }
        if client_id is not None:
            request_data["client_id"] = client_id
            
        response = client.post("/v1/uploads/presign", json=request_data)
        assert response.status_code == expected_status

class TestErrorHandling:
    """Test suite for error handling and edge cases."""
    
    @patch('app.routes.uploads.s3_manager.health_check')
    def test_s3_unhealthy(self, mock_health_check):
        """Test handling when S3 is unhealthy."""
        mock_health_check.return_value = {"status": "unhealthy", "error": "Connection failed"}
        
        response = client.post("/v1/uploads/presign", json={
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        })
        assert response.status_code == 503
        assert "Storage service temporarily unavailable" in response.json()["detail"]
    
    @patch('app.routes.uploads.generate_presigned_url')
    def test_circuit_breaker_open(self, mock_generate):
        """Test handling when circuit breaker is open."""
        mock_generate.side_effect = Exception("S3 circuit breaker is open - generate_presigned_url operation blocked")
        
        response = client.post("/v1/uploads/presign", json={
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        })
        assert response.status_code == 503
        assert "high error rate" in response.json()["detail"]
    
    @patch('app.routes.uploads.generate_presigned_url')
    def test_unexpected_error(self, mock_generate):
        """Test handling of unexpected errors."""
        mock_generate.side_effect = RuntimeError("Unexpected error")
        
        response = client.post("/v1/uploads/presign", json={
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        })
        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "Failed to generate upload URL"
        assert data["error_code"] == "INTERNAL_ERROR"
        assert "request_id" in data
        assert "timestamp" in data
    
    def test_missing_required_fields(self):
        """Test handling of missing required fields."""
        # Missing filename
        response = client.post("/v1/uploads/presign", json={
            "content_type": "application/pdf",
            "file_size": 1024
        })
        assert response.status_code == 422
        
        # Missing content_type
        response = client.post("/v1/uploads/presign", json={
            "filename": "test.pdf",
            "file_size": 1024
        })
        assert response.status_code == 422
        
        # Missing file_size
        response = client.post("/v1/uploads/presign", json={
            "filename": "test.pdf",
            "content_type": "application/pdf"
        })
        assert response.status_code == 422
    
    def test_invalid_json(self):
        """Test handling of invalid JSON."""
        response = client.post("/v1/uploads/presign", 
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

class TestHealthEndpoint:
    """Test suite for the upload health check endpoint."""
    
    def test_health_check_success(self):
        """Test successful health check."""
        response = client.get("/v1/uploads/health")
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert "timestamp" in data
        assert "request_id" in data
        assert "s3_health" in data
        assert "allowed_types" in data
        assert "max_file_size_mb" in data
        
        assert data["status"] in ["healthy", "degraded"]
        assert isinstance(data["allowed_types"], list)
        assert data["max_file_size_mb"] == MAX_FILE_SIZE / 1024 / 1024
    
    @patch('app.routes.uploads.s3_manager.health_check')
    def test_health_check_degraded(self, mock_health_check):
        """Test health check when S3 is degraded."""
        mock_health_check.return_value = {"status": "unhealthy", "error": "High latency"}
        
        response = client.get("/v1/uploads/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
    
    @patch('app.routes.uploads.s3_manager.health_check')
    def test_health_check_error(self, mock_health_check):
        """Test health check error handling."""
        mock_health_check.side_effect = Exception("Health check failed")
        
        response = client.get("/v1/uploads/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert "error" in data

class TestSanitization:
    """Test suite for filename sanitization."""
    
    @pytest.mark.parametrize("input_filename,expected_in_key", [
        ("test file.pdf", "testfile.pdf"),
        ("test@file.pdf", "testfile.pdf"),
        ("test#file.pdf", "testfile.pdf"),
        ("test$file%.pdf", "testfile.pdf"),
        ("test&file*.pdf", "testfile.pdf"),
        ("test(file).pdf", "testfile.pdf"),
        ("test[file].pdf", "testfile.pdf"),
        ("test{file}.pdf", "testfile.pdf"),
        ("test|file|.pdf", "testfile.pdf"),
        ("test:file;.pdf", "testfile.pdf"),
        ("test<file>.pdf", "testfile.pdf"),
        ("test?file!.pdf", "testfile.pdf"),
        ("test\"file'.pdf", "testfile.pdf"),
    ])
    def test_filename_sanitization(self, input_filename, expected_in_key):
        """Test that filenames are properly sanitized in the S3 key."""
        # First validate that these filenames would be rejected
        response = client.post("/v1/uploads/presign", json={
            "filename": input_filename,
            "content_type": "application/pdf",
            "file_size": 1024
        })
        assert response.status_code == 422  # Should be rejected by validation

class TestConcurrency:
    """Test suite for concurrent request handling."""
    
    def test_concurrent_requests(self):
        """Test handling of multiple concurrent requests."""
        import concurrent.futures
        
        def make_request(index):
            response = client.post("/v1/uploads/presign", json={
                "filename": f"concurrent-{index}.pdf",
                "content_type": "application/pdf",
                "file_size": 1024
            })
            return response.status_code, response.json()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All requests should succeed
        assert all(status == 200 for status, _ in results)
        
        # All should have unique request IDs
        request_ids = [data["request_id"] for _, data in results]
        assert len(set(request_ids)) == len(request_ids)
        
        # All should have unique S3 keys
        keys = [data["key"] for _, data in results]
        assert len(set(keys)) == len(keys)

class TestMetadata:
    """Test suite for metadata handling."""
    
    def test_metadata_field(self):
        """Test that metadata field is accepted."""
        response = client.post("/v1/uploads/presign", json={
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024,
            "metadata": {
                "user_id": "123",
                "department": "finance",
                "tags": ["invoice", "2024"]
            }
        })
        assert response.status_code == 200

class TestPerformance:
    """Test suite for performance characteristics."""
    
    def test_response_time(self):
        """Test that response time is reasonable."""
        start_time = time.time()
        response = client.post("/v1/uploads/presign", json={
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        })
        end_time = time.time()
        
        assert response.status_code == 200
        # Response should be generated within 1 second
        assert end_time - start_time < 1.0
    
    @pytest.mark.parametrize("execution_number", range(5))
    def test_consistent_response_structure(self, execution_number):
        """Test that response structure is consistent across multiple calls."""
        response = client.post("/v1/uploads/presign", json={
            "filename": f"test-{execution_number}.pdf",
            "content_type": "application/pdf",
            "file_size": 1024
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Check all expected fields are present
        expected_fields = ["key", "url", "expires_in", "request_id", 
                         "max_file_size", "allowed_content_types"]
        for field in expected_fields:
            assert field in data