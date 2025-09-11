"""
Comprehensive tests for hardened AWS S3 module.
Tests circuit breaker, retries with jitter, timeouts, and error handling.
"""
import pytest
import time
import threading
from unittest.mock import patch, MagicMock, call
from botocore.exceptions import ClientError, BotoCoreError, ConnectionError as BotoConnectionError
from app.aws import (
    CircuitBreaker, S3ClientManager, exponential_backoff_with_jitter,
    retry_with_exponential_backoff, s3_manager
)

class TestCircuitBreaker:
    """Test suite for enhanced circuit breaker."""
    
    def test_circuit_breaker_initial_state(self):
        """Test circuit breaker starts in closed state."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=5)
        assert cb.state == 'closed'
        assert cb.can_execute() is True
        assert cb.failure_count == 0
        assert cb.success_count == 0
    
    def test_circuit_breaker_opens_after_threshold(self):
        """Test circuit breaker opens after failure threshold."""
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=5)
        
        # Record failures up to threshold
        for i in range(3):
            assert cb.can_execute() is True
            cb.record_failure()
        
        # Circuit should now be open
        assert cb.state == 'open'
        assert cb.can_execute() is False
        
        # Check metrics
        status = cb.get_status()
        assert status['state'] == 'open'
        assert status['failure_count'] == 3
        assert status['metrics']['total_failures'] == 3
        assert status['metrics']['total_circuit_opens'] == 1
    
    def test_circuit_breaker_half_open_after_timeout(self):
        """Test circuit breaker transitions to half-open after timeout."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)  # 100ms timeout
        
        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == 'open'
        assert cb.can_execute() is False
        
        # Wait for recovery timeout
        time.sleep(0.15)
        
        # Should transition to half-open
        assert cb.can_execute() is True
        assert cb.state == 'half-open'
    
    def test_circuit_breaker_closes_after_success_threshold(self):
        """Test circuit breaker closes after success threshold in half-open state."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1, success_threshold=2)
        
        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == 'open'
        
        # Wait and transition to half-open
        time.sleep(0.15)
        assert cb.can_execute() is True
        assert cb.state == 'half-open'
        
        # Record successes
        cb.record_success()
        assert cb.state == 'half-open'  # Still half-open after 1 success
        
        cb.record_success()
        assert cb.state == 'closed'  # Closed after 2 successes
        assert cb.failure_count == 0
    
    def test_circuit_breaker_reopens_on_failure_in_half_open(self):
        """Test circuit breaker immediately reopens on failure in half-open state."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1, success_threshold=2)
        
        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        
        # Wait and transition to half-open
        time.sleep(0.15)
        assert cb.can_execute() is True
        assert cb.state == 'half-open'
        
        # Single failure in half-open should reopen
        cb.record_failure()
        assert cb.state == 'open'
        assert cb.can_execute() is False
    
    def test_circuit_breaker_thread_safety(self):
        """Test circuit breaker is thread-safe."""
        cb = CircuitBreaker(failure_threshold=50, recovery_timeout=10)
        
        def record_operations():
            for _ in range(100):
                if cb.can_execute():
                    # Simulate random success/failure
                    import random
                    if random.random() > 0.5:
                        cb.record_success()
                    else:
                        cb.record_failure()
        
        # Run multiple threads
        threads = []
        for _ in range(10):
            t = threading.Thread(target=record_operations)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Check consistency
        status = cb.get_status()
        metrics = status['metrics']
        assert metrics['total_successes'] + metrics['total_failures'] <= metrics['total_requests']

class TestExponentialBackoff:
    """Test suite for exponential backoff with jitter."""
    
    def test_exponential_backoff_calculation(self):
        """Test exponential backoff delay calculation."""
        # Test base case
        delay = exponential_backoff_with_jitter(0, base_delay=1.0, max_delay=60.0, jitter=0.0)
        assert delay == 1.0
        
        # Test exponential growth
        delay = exponential_backoff_with_jitter(1, base_delay=1.0, max_delay=60.0, jitter=0.0)
        assert delay == 2.0
        
        delay = exponential_backoff_with_jitter(2, base_delay=1.0, max_delay=60.0, jitter=0.0)
        assert delay == 4.0
        
        delay = exponential_backoff_with_jitter(3, base_delay=1.0, max_delay=60.0, jitter=0.0)
        assert delay == 8.0
    
    def test_exponential_backoff_max_delay(self):
        """Test exponential backoff respects max delay."""
        delay = exponential_backoff_with_jitter(10, base_delay=1.0, max_delay=30.0, jitter=0.0)
        assert delay == 30.0
    
    def test_exponential_backoff_jitter(self):
        """Test exponential backoff applies jitter correctly."""
        # With jitter, delay should vary
        delays = []
        for _ in range(10):
            delay = exponential_backoff_with_jitter(2, base_delay=1.0, max_delay=60.0, jitter=0.5)
            delays.append(delay)
        
        # Base delay for attempt 2 is 4.0
        # With 50% jitter, should be between 2.0 and 6.0
        assert all(2.0 <= d <= 6.0 for d in delays)
        # Delays should vary (extremely unlikely to get same value)
        assert len(set(delays)) > 1

class TestRetryDecorator:
    """Test suite for retry decorator."""
    
    def test_retry_success_on_first_attempt(self):
        """Test function succeeds on first attempt."""
        mock_func = MagicMock(return_value="success")
        
        @retry_with_exponential_backoff(max_attempts=3)
        def test_func():
            return mock_func()
        
        result = test_func()
        assert result == "success"
        assert mock_func.call_count == 1
    
    def test_retry_on_retriable_error(self):
        """Test function retries on retriable errors."""
        mock_func = MagicMock(side_effect=[
            ClientError({'Error': {'Code': 'ThrottlingException'}}, 'test'),
            ClientError({'Error': {'Code': 'ThrottlingException'}}, 'test'),
            "success"
        ])
        
        @retry_with_exponential_backoff(max_attempts=3, base_delay=0.01)
        def test_func():
            return mock_func()
        
        result = test_func()
        assert result == "success"
        assert mock_func.call_count == 3
    
    def test_retry_on_connection_error(self):
        """Test function retries on connection errors."""
        mock_func = MagicMock(side_effect=[
            BotoConnectionError("Connection failed"),
            BotoConnectionError("Connection failed"),
            "success"
        ])
        
        @retry_with_exponential_backoff(max_attempts=3, base_delay=0.01)
        def test_func():
            return mock_func()
        
        result = test_func()
        assert result == "success"
        assert mock_func.call_count == 3
    
    def test_retry_on_5xx_errors(self):
        """Test function retries on 5xx HTTP errors."""
        mock_func = MagicMock(side_effect=[
            ClientError({'Error': {'Code': 'InternalError'}, 
                        'ResponseMetadata': {'HTTPStatusCode': 503}}, 'test'),
            "success"
        ])
        
        @retry_with_exponential_backoff(max_attempts=3, base_delay=0.01)
        def test_func():
            return mock_func()
        
        result = test_func()
        assert result == "success"
        assert mock_func.call_count == 2
    
    def test_no_retry_on_non_retriable_error(self):
        """Test function doesn't retry on non-retriable errors."""
        mock_func = MagicMock(side_effect=ClientError(
            {'Error': {'Code': 'NoSuchBucket'}}, 'test'
        ))
        
        @retry_with_exponential_backoff(max_attempts=3)
        def test_func():
            return mock_func()
        
        with pytest.raises(ClientError) as exc_info:
            test_func()
        
        assert exc_info.value.response['Error']['Code'] == 'NoSuchBucket'
        assert mock_func.call_count == 1
    
    def test_max_attempts_exceeded(self):
        """Test function raises after max attempts."""
        mock_func = MagicMock(side_effect=ClientError(
            {'Error': {'Code': 'ThrottlingException'}}, 'test'
        ))
        
        @retry_with_exponential_backoff(max_attempts=3, base_delay=0.01)
        def test_func():
            return mock_func()
        
        with pytest.raises(ClientError):
            test_func()
        
        assert mock_func.call_count == 3

class TestS3ClientManager:
    """Test suite for enhanced S3 client manager."""
    
    @patch('app.aws.boto3.client')
    def test_client_creation_and_caching(self, mock_boto_client):
        """Test S3 client is created and cached properly."""
        manager = S3ClientManager()
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        
        # First call should create client
        client1 = manager.get_client()
        assert mock_boto_client.call_count == 1
        assert client1 == mock_client
        
        # Second call should return cached client
        client2 = manager.get_client()
        assert mock_boto_client.call_count == 1
        assert client2 == mock_client
    
    @patch('app.aws.boto3.client')
    def test_client_ttl_expiration(self, mock_boto_client):
        """Test S3 client is recreated after TTL expires."""
        manager = S3ClientManager()
        manager._client_ttl = 0.1  # 100ms TTL for testing
        
        mock_client1 = MagicMock()
        mock_client2 = MagicMock()
        mock_boto_client.side_effect = [mock_client1, mock_client2]
        
        # First client
        client1 = manager.get_client()
        assert client1 == mock_client1
        
        # Wait for TTL to expire
        time.sleep(0.15)
        
        # Should create new client
        client2 = manager.get_client()
        assert client2 == mock_client2
        assert mock_boto_client.call_count == 2
    
    def test_generate_presigned_url_validation(self):
        """Test presigned URL generation input validation."""
        manager = S3ClientManager()
        
        # Invalid key
        with pytest.raises(ValueError, match="S3 key must be a non-empty string"):
            manager.generate_presigned_url("", "application/pdf", 1024)
        
        with pytest.raises(ValueError, match="S3 key must be a non-empty string"):
            manager.generate_presigned_url(None, "application/pdf", 1024)
        
        # Invalid expiration
        with pytest.raises(ValueError, match="Expires in must be between"):
            manager.generate_presigned_url("test.pdf", "application/pdf", 1024, expires_in=0)
        
        with pytest.raises(ValueError, match="Expires in must be between"):
            manager.generate_presigned_url("test.pdf", "application/pdf", 1024, expires_in=700000)
    
    @patch('app.aws.boto3.client')
    def test_circuit_breaker_integration(self, mock_boto_client):
        """Test circuit breaker blocks operations when open."""
        manager = S3ClientManager()
        manager._circuit_breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=60)
        
        mock_client = MagicMock()
        mock_client.generate_presigned_url.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable'}}, 'test'
        )
        mock_boto_client.return_value = mock_client
        
        # First call should fail and open circuit
        with pytest.raises(ClientError):
            manager.generate_presigned_url("test.pdf", "application/pdf", 1024)
        
        # Circuit should now be open
        with pytest.raises(Exception, match="circuit breaker is open"):
            manager.generate_presigned_url("test.pdf", "application/pdf", 1024)
    
    def test_download_file_validation(self):
        """Test download file input validation."""
        manager = S3ClientManager()
        
        with pytest.raises(ValueError, match="S3 key must be a non-empty string"):
            manager.download_file("")
        
        with pytest.raises(ValueError, match="S3 key must be a non-empty string"):
            manager.download_file(None)
    
    @patch('app.aws.boto3.client')
    def test_download_file_size_limit(self, mock_boto_client):
        """Test download file size limit enforcement."""
        manager = S3ClientManager()
        mock_client = MagicMock()
        
        # Mock head_object to return large file size
        mock_client.head_object.return_value = {'ContentLength': 200 * 1024 * 1024}  # 200MB
        mock_boto_client.return_value = mock_client
        
        with pytest.raises(ValueError, match="exceeds maximum allowed size"):
            manager.download_file("large.pdf", max_size=100 * 1024 * 1024)  # 100MB limit
    
    @patch('app.aws.boto3.client')
    def test_download_file_not_found(self, mock_boto_client):
        """Test download file handles not found error."""
        manager = S3ClientManager()
        mock_client = MagicMock()
        
        # Mock head_object to return 404
        mock_client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'HeadObject'
        )
        mock_boto_client.return_value = mock_client
        
        with pytest.raises(FileNotFoundError, match="S3 object not found"):
            manager.download_file("missing.pdf", max_size=1024)
    
    def test_upload_file_validation(self):
        """Test upload file input validation."""
        manager = S3ClientManager()
        
        # Invalid key
        with pytest.raises(ValueError, match="S3 key must be a non-empty string"):
            manager.upload_file("", b"data", "application/pdf")
        
        # Invalid data type
        with pytest.raises(TypeError, match="Data must be bytes"):
            manager.upload_file("test.pdf", "not bytes", "application/pdf")
    
    @patch('app.aws.boto3.client')
    def test_upload_file_with_metadata(self, mock_boto_client):
        """Test upload file with metadata."""
        manager = S3ClientManager()
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        
        metadata = {"User-ID": "123", "Department": "Finance"}
        manager.upload_file("test.pdf", b"data", "application/pdf", metadata=metadata)
        
        # Check metadata was lowercased and passed
        mock_client.put_object.assert_called_once()
        call_args = mock_client.put_object.call_args[1]
        assert call_args['Metadata'] == {'user-id': '123', 'department': 'Finance'}
    
    def test_delete_file_validation(self):
        """Test delete file input validation."""
        manager = S3ClientManager()
        
        with pytest.raises(ValueError, match="S3 key must be a non-empty string"):
            manager.delete_file("")
        
        with pytest.raises(ValueError, match="S3 key must be a non-empty string"):
            manager.delete_file(None)
    
    @patch('app.aws.boto3.client')
    def test_operation_statistics(self, mock_boto_client):
        """Test operation statistics tracking."""
        manager = S3ClientManager()
        mock_client = MagicMock()
        mock_client.head_bucket.return_value = True
        mock_client.delete_object.return_value = {}
        mock_boto_client.return_value = mock_client
        
        # Successful operation
        manager.delete_file("test.pdf")
        
        stats = manager.get_stats()
        assert stats['operation_stats']['total_operations'] == 1
        assert stats['operation_stats']['successful_operations'] == 1
        assert stats['operation_stats']['failed_operations'] == 0
        assert stats['operation_stats']['avg_response_time'] > 0
    
    @patch('app.aws.boto3.client')
    def test_health_check(self, mock_boto_client):
        """Test health check functionality."""
        manager = S3ClientManager()
        mock_client = MagicMock()
        mock_client.head_bucket.return_value = True
        mock_client.generate_presigned_url.return_value = "https://example.com/upload"
        mock_boto_client.return_value = mock_client
        
        health = manager.health_check()
        
        assert health['status'] == 'healthy'
        assert 'response_time_ms' in health
        assert 'circuit_breaker' in health
        assert 'operation_stats' in health
        assert health['circuit_breaker']['state'] == 'closed'
    
    @patch('app.aws.boto3.client')
    def test_health_check_caching(self, mock_boto_client):
        """Test health check result caching."""
        manager = S3ClientManager()
        manager._health_cache_ttl = 1  # 1 second cache
        mock_client = MagicMock()
        mock_client.head_bucket.return_value = True
        mock_client.generate_presigned_url.return_value = "https://example.com/upload"
        mock_boto_client.return_value = mock_client
        
        # First call
        health1 = manager.health_check()
        
        # Second call should return cached result
        health2 = manager.health_check()
        assert health1 == health2
        assert mock_client.head_bucket.call_count == 1
        
        # Wait for cache to expire
        time.sleep(1.1)
        
        # Third call should hit S3 again
        health3 = manager.health_check()
        assert mock_client.head_bucket.call_count == 2
    
    def test_reset_stats(self):
        """Test statistics reset."""
        manager = S3ClientManager()
        
        # Modify stats
        manager._operation_stats['total_operations'] = 100
        manager._operation_stats['successful_operations'] = 90
        
        # Reset
        manager.reset_stats()
        
        stats = manager.get_stats()
        assert stats['operation_stats']['total_operations'] == 0
        assert stats['operation_stats']['successful_operations'] == 0
    
    def test_reset_circuit_breaker(self):
        """Test circuit breaker reset."""
        manager = S3ClientManager()
        
        # Open circuit breaker
        manager._circuit_breaker.state = 'open'
        manager._circuit_breaker.failure_count = 5
        
        # Reset
        manager.reset_circuit_breaker()
        
        status = manager._circuit_breaker.get_status()
        assert status['state'] == 'closed'
        assert status['failure_count'] == 0

class TestIdempotency:
    """Test suite for idempotent operation handling."""
    
    @patch('app.aws.boto3.client')
    def test_idempotent_operations_retry(self, mock_boto_client):
        """Test idempotent operations are retried."""
        manager = S3ClientManager()
        mock_client = MagicMock()
        
        # Fail twice, then succeed
        mock_client.delete_object.side_effect = [
            ClientError({'Error': {'Code': 'ServiceUnavailable'}}, 'delete'),
            ClientError({'Error': {'Code': 'ServiceUnavailable'}}, 'delete'),
            {}
        ]
        mock_boto_client.return_value = mock_client
        
        # Should succeed after retries
        manager.delete_file("test.pdf")
        assert mock_client.delete_object.call_count == 3
    
    @patch('app.aws.boto3.client')
    def test_non_idempotent_operations_no_retry(self, mock_boto_client):
        """Test non-idempotent operations are not retried by default."""
        manager = S3ClientManager()
        mock_client = MagicMock()
        
        # Upload should fail immediately without retry
        mock_client.put_object.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable'}}, 'put'
        )
        mock_boto_client.return_value = mock_client
        
        with pytest.raises(ClientError):
            manager.upload_file("test.pdf", b"data", "application/pdf")
        
        # Should not retry non-idempotent operation
        assert mock_client.put_object.call_count == 1

class TestThreadSafety:
    """Test suite for thread safety."""
    
    @patch('app.aws.boto3.client')
    def test_concurrent_client_creation(self, mock_boto_client):
        """Test concurrent client creation is thread-safe."""
        manager = S3ClientManager()
        mock_boto_client.return_value = MagicMock()
        
        def get_client_multiple_times():
            for _ in range(10):
                manager.get_client()
        
        threads = []
        for _ in range(10):
            t = threading.Thread(target=get_client_multiple_times)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # Should only create one client despite concurrent access
        assert mock_boto_client.call_count == 1
    
    @patch('app.aws.boto3.client')
    def test_concurrent_operations(self, mock_boto_client):
        """Test concurrent operations maintain correct statistics."""
        manager = S3ClientManager()
        mock_client = MagicMock()
        mock_client.delete_object.return_value = {}
        mock_boto_client.return_value = mock_client
        
        def perform_operations():
            for _ in range(10):
                try:
                    manager.delete_file(f"test-{threading.current_thread().ident}.pdf")
                except:
                    pass
        
        threads = []
        for _ in range(5):
            t = threading.Thread(target=perform_operations)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        stats = manager.get_stats()
        # All operations should be accounted for
        assert stats['operation_stats']['total_operations'] == 50