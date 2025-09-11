"""
Enhanced test suite for worker modules with comprehensive error handling and mocking.
Tests circuit breaker, retries, timeouts, and resource management.
"""
import pytest
import time
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path
from botocore.exceptions import ClientError, BotoCoreError

from worker.aws_client import WorkerS3Client, CircuitBreaker
from worker.services import DocumentProcessor, ResourceManager, TimeoutError, ProcessingError
from worker.models import ProcessingStatus, EventType


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_circuit_breaker_initial_state(self):
        """Test circuit breaker starts in closed state."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        
        assert cb.state == 'closed'
        assert cb.failure_count == 0
        assert cb.can_execute() is True
        
        status = cb.get_status()
        assert status['state'] == 'closed'
        assert status['failure_count'] == 0

    def test_circuit_breaker_failure_tracking(self):
        """Test circuit breaker tracks failures correctly."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        
        # Record failures
        cb.record_failure()
        assert cb.failure_count == 1
        assert cb.state == 'closed'
        assert cb.can_execute() is True
        
        cb.record_failure()
        assert cb.failure_count == 2
        assert cb.state == 'closed'
        
        # Third failure should open the circuit
        cb.record_failure()
        assert cb.failure_count == 3
        assert cb.state == 'open'
        assert cb.can_execute() is False

    def test_circuit_breaker_recovery(self):
        """Test circuit breaker recovery after timeout."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)  # 1 second recovery
        
        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == 'open'
        assert cb.can_execute() is False
        
        # Wait for recovery timeout
        time.sleep(1.1)
        
        # Should transition to half-open
        assert cb.can_execute() is True
        assert cb.state == 'half-open'
        
        # Success should close the circuit
        cb.record_success()
        assert cb.state == 'closed'
        assert cb.failure_count == 0

    def test_circuit_breaker_half_open_failure(self):
        """Test circuit breaker behavior when half-open operation fails."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        
        # Open the circuit
        cb.record_failure()
        assert cb.state == 'open'
        
        # Wait for recovery
        time.sleep(0.2)
        assert cb.can_execute() is True  # Should be half-open
        
        # Another failure should open it again
        cb.record_failure()
        assert cb.state == 'open'
        assert cb.can_execute() is False


class TestWorkerS3Client:
    """Test enhanced worker S3 client."""

    @pytest.fixture
    def s3_client(self):
        """Create S3 client with mocked boto3."""
        with patch('worker.aws_client.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            
            # Mock successful bucket access verification
            mock_client.head_bucket.return_value = {}
            
            client = WorkerS3Client()
            client.client = mock_client
            return client

    def test_s3_client_initialization(self, s3_client):
        """Test S3 client initializes correctly."""
        assert s3_client.s3_bucket == 'ledger-lift'
        assert s3_client._circuit_breaker.state == 'closed'
        assert s3_client._operation_stats['total_operations'] == 0

    def test_download_file_success(self, s3_client):
        """Test successful file download."""
        mock_response = {'Body': Mock()}
        mock_response['Body'].read.return_value = b'test content'
        s3_client.client.get_object.return_value = mock_response
        
        result = s3_client.download_file('test/file.pdf')
        
        assert result == b'test content'
        s3_client.client.get_object.assert_called_once_with(
            Bucket='ledger-lift', 
            Key='test/file.pdf'
        )
        assert s3_client._operation_stats['successful_operations'] == 1
        assert s3_client._circuit_breaker.state == 'closed'

    def test_download_file_validation(self, s3_client):
        """Test download file input validation."""
        with pytest.raises(ValueError, match="S3 key cannot be empty"):
            s3_client.download_file("")
        
        with pytest.raises(ValueError, match="S3 key cannot be empty"):
            s3_client.download_file("   ")
        
        with pytest.raises(ValueError, match="S3 key cannot be empty"):
            s3_client.download_file(None)

    def test_download_file_with_retry(self, s3_client):
        """Test download file with retry on transient failure."""
        mock_response = {'Body': Mock()}
        mock_response['Body'].read.return_value = b'test content'
        
        # First call fails, second succeeds
        s3_client.client.get_object.side_effect = [
            ClientError({'Error': {'Code': '500'}}, 'GetObject'),
            mock_response
        ]
        
        with patch('time.sleep'):  # Speed up test
            result = s3_client.download_file('test/file.pdf')
        
        assert result == b'test content'
        assert s3_client.client.get_object.call_count == 2
        assert s3_client._operation_stats['successful_operations'] == 1

    def test_download_file_circuit_breaker_open(self, s3_client):
        """Test download file when circuit breaker is open."""
        # Open the circuit breaker
        s3_client._circuit_breaker.state = 'open'
        
        with pytest.raises(Exception, match="circuit breaker is open"):
            s3_client.download_file('test/file.pdf')

    def test_upload_file_success(self, s3_client):
        """Test successful file upload."""
        s3_client.client.put_object.return_value = {}
        
        s3_client.upload_file('test/file.pdf', b'test content', 'application/pdf')
        
        s3_client.client.put_object.assert_called_once_with(
            Bucket='ledger-lift',
            Key='test/file.pdf',
            Body=b'test content',
            ContentType='application/pdf',
            ServerSideEncryption=None
        )
        assert s3_client._operation_stats['successful_operations'] == 1

    def test_upload_file_validation(self, s3_client):
        """Test upload file input validation."""
        with pytest.raises(ValueError, match="S3 key cannot be empty"):
            s3_client.upload_file("", b'data', 'application/pdf')
        
        with pytest.raises(ValueError, match="Data cannot be empty"):
            s3_client.upload_file("key", b'', 'application/pdf')
        
        with pytest.raises(ValueError, match="Content type cannot be empty"):
            s3_client.upload_file("key", b'data', "")

    def test_file_exists_true(self, s3_client):
        """Test file exists check when file exists."""
        s3_client.client.head_object.return_value = {}
        
        result = s3_client.file_exists('test/file.pdf')
        
        assert result is True
        s3_client.client.head_object.assert_called_once_with(
            Bucket='ledger-lift',
            Key='test/file.pdf'
        )

    def test_file_exists_false(self, s3_client):
        """Test file exists check when file doesn't exist."""
        s3_client.client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )
        
        result = s3_client.file_exists('test/file.pdf')
        
        assert result is False

    def test_get_file_metadata(self, s3_client):
        """Test getting file metadata."""
        s3_client.client.head_object.return_value = {
            'ContentLength': 1024,
            'LastModified': '2023-01-01T00:00:00Z',
            'ContentType': 'application/pdf',
            'ETag': '"abc123"'
        }
        
        result = s3_client.get_file_metadata('test/file.pdf')
        
        expected = {
            'size': 1024,
            'last_modified': '2023-01-01T00:00:00Z',
            'content_type': 'application/pdf',
            'etag': 'abc123'
        }
        assert result == expected

    def test_health_check_healthy(self, s3_client):
        """Test health check when S3 is healthy."""
        s3_client.client.head_bucket.return_value = {}
        
        result = s3_client.health_check()
        
        assert result['status'] == 'healthy'
        assert 'response_time_ms' in result
        assert 'circuit_breaker' in result
        assert 'operation_stats' in result

    def test_health_check_unhealthy(self, s3_client):
        """Test health check when S3 is unhealthy."""
        s3_client.client.head_bucket.side_effect = Exception("Connection failed")
        
        result = s3_client.health_check()
        
        assert result['status'] == 'unhealthy'
        assert 'error' in result
        assert result['error'] == 'Connection failed'

    def test_operation_stats_tracking(self, s3_client):
        """Test that operation statistics are tracked correctly."""
        # Successful operation
        mock_response = {'Body': Mock()}
        mock_response['Body'].read.return_value = b'test'
        s3_client.client.get_object.return_value = mock_response
        
        s3_client.download_file('test.pdf')
        
        stats = s3_client.get_stats()
        assert stats['operation_stats']['total_operations'] == 1
        assert stats['operation_stats']['successful_operations'] == 1
        assert stats['operation_stats']['failed_operations'] == 0
        assert stats['operation_stats']['avg_response_time'] > 0
        
        # Failed operation
        s3_client.client.get_object.side_effect = Exception("Failed")
        
        with pytest.raises(Exception):
            s3_client.download_file('test2.pdf')
        
        stats = s3_client.get_stats()
        assert stats['operation_stats']['total_operations'] == 2
        assert stats['operation_stats']['successful_operations'] == 1
        assert stats['operation_stats']['failed_operations'] == 1

    def test_reset_stats(self, s3_client):
        """Test statistics reset functionality."""
        # Generate some stats
        mock_response = {'Body': Mock()}
        mock_response['Body'].read.return_value = b'test'
        s3_client.client.get_object.return_value = mock_response
        s3_client.download_file('test.pdf')
        
        # Reset stats
        s3_client.reset_stats()
        
        stats = s3_client.get_stats()
        assert stats['operation_stats']['total_operations'] == 0
        assert stats['operation_stats']['successful_operations'] == 0
        assert stats['operation_stats']['failed_operations'] == 0


class TestResourceManager:
    """Test resource manager for temporary file cleanup."""

    def test_temp_file_creation_and_cleanup(self):
        """Test temporary file creation and cleanup."""
        rm = ResourceManager()
        
        # Create temp file
        temp_path = rm.create_temp_file(suffix='.pdf')
        assert os.path.exists(temp_path)
        assert temp_path.endswith('.pdf')
        assert len(rm.temp_files) == 1
        
        # Write some data
        with open(temp_path, 'w') as f:
            f.write('test data')
        
        # Cleanup
        rm.cleanup()
        assert not os.path.exists(temp_path)
        assert len(rm.temp_files) == 0

    def test_temp_dir_creation_and_cleanup(self):
        """Test temporary directory creation and cleanup."""
        rm = ResourceManager()
        
        # Create temp directory
        temp_dir = rm.create_temp_dir()
        assert os.path.exists(temp_dir)
        assert os.path.isdir(temp_dir)
        assert len(rm.temp_dirs) == 1
        
        # Create a file in the directory
        test_file = os.path.join(temp_dir, 'test.txt')
        with open(test_file, 'w') as f:
            f.write('test')
        
        # Cleanup
        rm.cleanup()
        assert not os.path.exists(temp_dir)
        assert not os.path.exists(test_file)
        assert len(rm.temp_dirs) == 0

    def test_cleanup_with_missing_files(self):
        """Test cleanup handles missing files gracefully."""
        rm = ResourceManager()
        
        # Add non-existent file to tracking
        rm.temp_files.append('/nonexistent/file.txt')
        rm.temp_dirs.append('/nonexistent/dir')
        
        # Should not raise exception
        rm.cleanup()
        assert len(rm.temp_files) == 0
        assert len(rm.temp_dirs) == 0

    def test_cleanup_with_permission_errors(self):
        """Test cleanup handles permission errors gracefully."""
        rm = ResourceManager()
        
        # Create temp file
        temp_path = rm.create_temp_file()
        
        # Mock os.unlink to raise permission error
        with patch('os.unlink', side_effect=PermissionError("Access denied")):
            rm.cleanup()  # Should not raise exception
        
        # File list should still be cleared
        assert len(rm.temp_files) == 0


class TestDocumentProcessor:
    """Test enhanced document processor."""

    @pytest.fixture
    def processor(self):
        """Create document processor with mocked dependencies."""
        with patch('worker.services.WorkerDatabase') as mock_db_class, \
             patch('worker.services.WorkerS3Client') as mock_s3_class:
            
            mock_db = Mock()
            mock_s3 = Mock()
            mock_db_class.return_value = mock_db
            mock_s3_class.return_value = mock_s3
            
            processor = DocumentProcessor()
            processor.db = mock_db
            processor.s3 = mock_s3
            
            return processor

    @pytest.fixture
    def mock_document(self):
        """Create mock document object."""
        doc = Mock()
        doc.id = 'doc-123'
        doc.s3_key = 'raw/test.pdf'
        doc.original_filename = 'test.pdf'
        return doc

    def test_process_document_validation(self, processor):
        """Test document processing input validation."""
        with pytest.raises(ValueError, match="Document ID cannot be empty"):
            processor.process_document("")
        
        with pytest.raises(ValueError, match="Document ID cannot be empty"):
            processor.process_document("   ")

    def test_process_document_success(self, processor, mock_document):
        """Test successful document processing."""
        # Setup mocks
        processor.db.get_document.return_value = mock_document
        processor.s3.health_check.return_value = {'status': 'healthy'}
        processor.s3.download_file.return_value = b'%PDF-1.4\ntest pdf content'
        
        with patch('worker.services.render_pdf_preview') as mock_render, \
             patch('worker.services.extract_tables_stub') as mock_extract, \
             patch('builtins.open', mock_open()):
            
            # Mock preview rendering
            mock_preview_paths = [Path('/tmp/preview1.png'), Path('/tmp/preview2.png')]
            mock_render.return_value = mock_preview_paths
            
            # Mock preview file existence and reading
            with patch.object(Path, 'exists', return_value=True), \
                 patch.object(Path, 'stat') as mock_stat:
                
                mock_stat.return_value.st_size = 1024
                
                # Mock table extraction
                mock_extract.return_value = [{'table': 1}, {'table': 2}]
                
                # Mock file reading for previews
                with patch('builtins.open', mock_open(read_data=b'png data')):
                    result = processor.process_document('doc-123', timeout_seconds=60)
        
        # Verify successful processing
        assert result['success'] is True
        assert result['doc_id'] == 'doc-123'
        assert 'processing_time' in result
        assert 'stages_completed' in result
        assert len(result['stages_completed']) > 0
        
        # Verify database calls
        processor.db.update_document_status.assert_any_call('doc-123', ProcessingStatus.PROCESSING)
        processor.db.update_document_status.assert_any_call('doc-123', ProcessingStatus.COMPLETED)
        processor.db.create_page.assert_called()

    def test_process_document_not_found(self, processor):
        """Test processing when document is not found."""
        processor.db.get_document.return_value = None
        
        with pytest.raises(ProcessingError, match="Document not found"):
            processor.process_document('nonexistent-doc')

    def test_process_document_invalid_pdf(self, processor, mock_document):
        """Test processing with invalid PDF content."""
        processor.db.get_document.return_value = mock_document
        processor.s3.health_check.return_value = {'status': 'healthy'}
        processor.s3.download_file.return_value = b'not a pdf'  # Invalid PDF
        
        with pytest.raises(ProcessingError, match="not a valid PDF"):
            processor.process_document('doc-123')

    def test_process_document_empty_pdf(self, processor, mock_document):
        """Test processing with empty PDF content."""
        processor.db.get_document.return_value = mock_document
        processor.s3.health_check.return_value = {'status': 'healthy'}
        processor.s3.download_file.return_value = b''  # Empty content
        
        with pytest.raises(ProcessingError, match="Downloaded file is empty"):
            processor.process_document('doc-123')

    def test_process_document_s3_unhealthy(self, processor, mock_document):
        """Test processing when S3 is unhealthy."""
        processor.db.get_document.return_value = mock_document
        processor.s3.health_check.return_value = {
            'status': 'unhealthy', 
            'error': 'Connection timeout'
        }
        
        with pytest.raises(ProcessingError, match="S3 unhealthy"):
            processor.process_document('doc-123')

    def test_process_document_pdf_too_large(self, processor, mock_document):
        """Test processing with PDF that's too large."""
        processor.db.get_document.return_value = mock_document
        processor.s3.health_check.return_value = {'status': 'healthy'}
        
        # Create large PDF content (over default 100MB limit)
        large_pdf = b'%PDF-1.4\n' + b'x' * (101 * 1024 * 1024)
        processor.s3.download_file.return_value = large_pdf
        
        with pytest.raises(ProcessingError, match="PDF too large"):
            processor.process_document('doc-123')

    def test_process_document_render_timeout(self, processor, mock_document):
        """Test processing with PDF rendering timeout."""
        processor.db.get_document.return_value = mock_document
        processor.s3.health_check.return_value = {'status': 'healthy'}
        processor.s3.download_file.return_value = b'%PDF-1.4\ntest content'
        
        with patch('worker.services.render_pdf_preview') as mock_render, \
             patch('builtins.open', mock_open()):
            
            # Mock timeout in render function
            def slow_render(*args):
                time.sleep(2)  # Simulate slow operation
                return []
            
            mock_render.side_effect = slow_render
            
            with pytest.raises(ProcessingError, match="timed out"):
                processor.process_document('doc-123', timeout_seconds=1)

    def test_process_document_preview_upload_failure(self, processor, mock_document):
        """Test processing with preview upload failure."""
        processor.db.get_document.return_value = mock_document
        processor.s3.health_check.return_value = {'status': 'healthy'}
        processor.s3.download_file.return_value = b'%PDF-1.4\ntest content'
        
        with patch('worker.services.render_pdf_preview') as mock_render, \
             patch('worker.services.extract_tables_stub') as mock_extract, \
             patch('builtins.open', mock_open()):
            
            mock_preview_paths = [Path('/tmp/preview1.png')]
            mock_render.return_value = mock_preview_paths
            mock_extract.return_value = []
            
            with patch.object(Path, 'exists', return_value=True), \
                 patch.object(Path, 'stat') as mock_stat:
                
                mock_stat.return_value.st_size = 1024
                
                # Mock S3 upload failure
                processor.s3.upload_file.side_effect = Exception("Upload failed")
                
                with patch('builtins.open', mock_open(read_data=b'png data')):
                    with pytest.raises(ProcessingError, match="No previews were successfully uploaded"):
                        processor.process_document('doc-123')

    def test_process_document_graceful_table_extraction_failure(self, processor, mock_document):
        """Test that table extraction failure doesn't stop processing."""
        processor.db.get_document.return_value = mock_document
        processor.s3.health_check.return_value = {'status': 'healthy'}
        processor.s3.download_file.return_value = b'%PDF-1.4\ntest content'
        
        with patch('worker.services.render_pdf_preview') as mock_render, \
             patch('worker.services.extract_tables_stub') as mock_extract, \
             patch('builtins.open', mock_open()):
            
            mock_preview_paths = [Path('/tmp/preview1.png')]
            mock_render.return_value = mock_preview_paths
            
            # Mock table extraction failure
            mock_extract.side_effect = Exception("Extraction failed")
            
            with patch.object(Path, 'exists', return_value=True), \
                 patch.object(Path, 'stat') as mock_stat:
                
                mock_stat.return_value.st_size = 1024
                
                with patch('builtins.open', mock_open(read_data=b'png data')):
                    result = processor.process_document('doc-123')
        
        # Should still succeed despite table extraction failure
        assert result['success'] is True
        assert result['table_count'] == 0  # No tables extracted due to failure

    def test_processing_stats_tracking(self, processor, mock_document):
        """Test that processing statistics are tracked correctly."""
        processor.db.get_document.return_value = mock_document
        processor.s3.health_check.return_value = {'status': 'healthy'}
        processor.s3.download_file.return_value = b'%PDF-1.4\ntest content'
        
        with patch('worker.services.render_pdf_preview', return_value=[]), \
             patch('worker.services.extract_tables_stub', return_value=[]), \
             patch('builtins.open', mock_open()):
            
            processor.process_document('doc-123')
        
        stats = processor.get_processing_stats()
        assert stats['processing_stats']['total_processed'] == 1
        assert stats['processing_stats']['successful_processed'] == 1
        assert stats['processing_stats']['failed_processed'] == 0
        assert stats['processing_stats']['avg_processing_time'] > 0

    def test_processing_stats_failure_tracking(self, processor):
        """Test that processing failure statistics are tracked."""
        processor.db.get_document.return_value = None  # Document not found
        
        with pytest.raises(ProcessingError):
            processor.process_document('nonexistent')
        
        stats = processor.get_processing_stats()
        assert stats['processing_stats']['total_processed'] == 1
        assert stats['processing_stats']['successful_processed'] == 0
        assert stats['processing_stats']['failed_processed'] == 1

    def test_health_check(self, processor):
        """Test processor health check."""
        processor.s3.health_check.return_value = {'status': 'healthy'}
        
        result = processor.health_check()
        
        assert result['status'] == 'healthy'
        assert 's3_health' in result
        assert 'database_healthy' in result
        assert 'processing_stats' in result

    def test_reset_stats(self, processor):
        """Test statistics reset functionality."""
        # Generate some stats
        processor._processing_stats['total_processed'] = 5
        processor._processing_stats['successful_processed'] = 3
        
        processor.reset_stats()
        
        stats = processor.get_processing_stats()
        assert stats['processing_stats']['total_processed'] == 0
        assert stats['processing_stats']['successful_processed'] == 0


class TestIntegrationScenarios:
    """Test integration scenarios with multiple components."""

    @pytest.fixture
    def full_processor(self):
        """Create processor with real resource manager but mocked external deps."""
        with patch('worker.services.WorkerDatabase') as mock_db_class, \
             patch('worker.services.WorkerS3Client') as mock_s3_class:
            
            mock_db = Mock()
            mock_s3 = Mock()
            mock_db_class.return_value = mock_db
            mock_s3_class.return_value = mock_s3
            
            processor = DocumentProcessor()
            processor.db = mock_db
            processor.s3 = mock_s3
            
            return processor

    def test_end_to_end_processing_with_cleanup(self, full_processor):
        """Test end-to-end processing with proper resource cleanup."""
        # Setup document
        mock_doc = Mock()
        mock_doc.id = 'doc-123'
        mock_doc.s3_key = 'raw/test.pdf'
        mock_doc.original_filename = 'test.pdf'
        
        full_processor.db.get_document.return_value = mock_doc
        full_processor.s3.health_check.return_value = {'status': 'healthy'}
        full_processor.s3.download_file.return_value = b'%PDF-1.4\ntest pdf content'
        
        # Track created temporary files
        created_files = []
        
        def track_temp_file(*args, **kwargs):
            fd, path = tempfile.mkstemp(*args, **kwargs)
            os.close(fd)
            created_files.append(path)
            return path
        
        with patch('worker.services.render_pdf_preview') as mock_render, \
             patch('worker.services.extract_tables_stub') as mock_extract, \
             patch('tempfile.mkstemp', side_effect=track_temp_file):
            
            mock_preview_paths = [Path('/tmp/preview1.png'), Path('/tmp/preview2.png')]
            mock_render.return_value = mock_preview_paths
            mock_extract.return_value = []
            
            with patch.object(Path, 'exists', return_value=True), \
                 patch.object(Path, 'stat') as mock_stat, \
                 patch('builtins.open', mock_open(read_data=b'png data')):
                
                mock_stat.return_value.st_size = 1024
                
                result = full_processor.process_document('doc-123')
        
        # Verify processing succeeded
        assert result['success'] is True
        
        # Verify temporary files were cleaned up
        for file_path in created_files:
            assert not os.path.exists(file_path)

    def test_circuit_breaker_integration(self):
        """Test circuit breaker integration across multiple operations."""
        with patch('worker.aws_client.boto3.client') as mock_boto3:
            mock_client = Mock()
            mock_boto3.return_value = mock_client
            mock_client.head_bucket.return_value = {}
            
            s3_client = WorkerS3Client()
            s3_client.client = mock_client
            
            # Simulate multiple failures to open circuit breaker
            mock_client.get_object.side_effect = ClientError(
                {'Error': {'Code': '500'}}, 'GetObject'
            )
            
            # First few failures should retry
            for _ in range(3):
                with pytest.raises(Exception):
                    with patch('time.sleep'):  # Speed up test
                        s3_client.download_file('test.pdf')
            
            # After enough failures, circuit should open
            assert s3_client._circuit_breaker.state == 'open'
            
            # Next operation should be blocked immediately
            with pytest.raises(Exception, match="circuit breaker is open"):
                s3_client.download_file('test2.pdf')

    def test_timeout_and_cleanup_integration(self, full_processor):
        """Test timeout handling with proper resource cleanup."""
        mock_doc = Mock()
        mock_doc.id = 'doc-123'
        mock_doc.s3_key = 'raw/test.pdf'
        mock_doc.original_filename = 'test.pdf'
        
        full_processor.db.get_document.return_value = mock_doc
        full_processor.s3.health_check.return_value = {'status': 'healthy'}
        full_processor.s3.download_file.return_value = b'%PDF-1.4\ntest content'
        
        # Track created files
        created_files = []
        
        def track_and_slow_render(path):
            # Track the temp file that was created
            created_files.append(path)
            # Simulate slow operation that will timeout
            time.sleep(2)
            return []
        
        with patch('worker.services.render_pdf_preview', side_effect=track_and_slow_render), \
             patch('builtins.open', mock_open()):
            
            with pytest.raises(ProcessingError, match="timed out"):
                full_processor.process_document('doc-123', timeout_seconds=1)
        
        # Verify that failure was logged properly
        full_processor.db.update_document_status.assert_called_with('doc-123', ProcessingStatus.FAILED)


def mock_open(read_data=b''):
    """Helper to create a mock for file operations."""
    mock_file = MagicMock()
    mock_file.read.return_value = read_data
    mock_file.__enter__.return_value = mock_file
    mock_file.__exit__.return_value = None
    return MagicMock(return_value=mock_file)