import asyncio
import logging
import time
import random
import threading
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, AsyncGenerator, Callable, TypeVar
from functools import wraps
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, ConnectionError as BotoConnectionError
from .settings import settings

logger = logging.getLogger(__name__)

T = TypeVar('T')

class CircuitBreaker:
    """Enhanced circuit breaker for S3 operations with thread safety and metrics."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60, 
                 success_threshold: int = 2):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold  # Successes needed to close from half-open
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.state = 'closed'  # closed, open, half-open
        self._lock = threading.Lock()
        
        # Metrics
        self.total_requests = 0
        self.total_failures = 0
        self.total_successes = 0
        self.total_circuit_opens = 0
    
    def can_execute(self) -> bool:
        """Check if operation can be executed based on circuit breaker state."""
        with self._lock:
            self.total_requests += 1
            
            if self.state == 'closed':
                return True
            elif self.state == 'open':
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    logger.info("Circuit breaker transitioning from open to half-open")
                    self.state = 'half-open'
                    self.success_count = 0
                    return True
                return False
            else:  # half-open
                return True
    
    def record_success(self):
        """Record successful operation."""
        with self._lock:
            self.total_successes += 1
            
            if self.state == 'half-open':
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    logger.info("Circuit breaker closing after successful operations")
                    self.state = 'closed'
                    self.failure_count = 0
            elif self.state == 'closed':
                self.failure_count = 0
    
    def record_failure(self):
        """Record failed operation."""
        with self._lock:
            self.total_failures += 1
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == 'half-open':
                # Immediately open on failure in half-open state
                self.state = 'open'
                self.total_circuit_opens += 1
                logger.warning("Circuit breaker opened from half-open state after failure")
            elif self.failure_count >= self.failure_threshold:
                self.state = 'open'
                self.total_circuit_opens += 1
                logger.warning(f"S3 circuit breaker opened after {self.failure_count} failures")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        with self._lock:
            return {
                'state': self.state,
                'failure_count': self.failure_count,
                'success_count': self.success_count,
                'last_failure_time': self.last_failure_time,
                'failure_threshold': self.failure_threshold,
                'success_threshold': self.success_threshold,
                'recovery_timeout': self.recovery_timeout,
                'metrics': {
                    'total_requests': self.total_requests,
                    'total_successes': self.total_successes,
                    'total_failures': self.total_failures,
                    'total_circuit_opens': self.total_circuit_opens,
                    'failure_rate': self.total_failures / max(1, self.total_requests)
                }
            }

def exponential_backoff_with_jitter(attempt: int, base_delay: float = 1.0, 
                                  max_delay: float = 60.0, jitter: float = 0.1) -> float:
    """Calculate exponential backoff delay with jitter.
    
    Args:
        attempt: Current retry attempt (0-based)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        jitter: Jitter factor (0.0 to 1.0)
    
    Returns:
        Delay in seconds with jitter applied
    """
    # Calculate exponential delay
    delay = min(base_delay * (2 ** attempt), max_delay)
    
    # Add jitter (±jitter% of delay)
    jitter_range = delay * jitter
    actual_delay = delay + random.uniform(-jitter_range, jitter_range)
    
    return max(0, actual_delay)


def retry_with_exponential_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: float = 0.1,
    retriable_exceptions: tuple = (ClientError, BotoConnectionError, BotoCoreError),
    retriable_error_codes: tuple = ('ThrottlingException', 'ProvisionedThroughputExceededException', 
                                   'RequestLimitExceeded', 'ServiceUnavailable', '503')
):
    """Decorator for retrying operations with exponential backoff and jitter."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except retriable_exceptions as e:
                    last_exception = e
                    
                    # Check if this is a retriable error
                    is_retriable = False
                    
                    if isinstance(e, ClientError):
                        error_code = e.response.get('Error', {}).get('Code', '')
                        if error_code in retriable_error_codes:
                            is_retriable = True
                        # Also check HTTP status code
                        status_code = e.response.get('ResponseMetadata', {}).get('HTTPStatusCode', 0)
                        if status_code in [429, 500, 502, 503, 504]:
                            is_retriable = True
                    else:
                        # For other exceptions, always retry
                        is_retriable = True
                    
                    if not is_retriable:
                        logger.warning(f"Non-retriable error in {func.__name__}: {e}")
                        raise
                    
                    if attempt < max_attempts - 1:
                        delay = exponential_backoff_with_jitter(attempt, base_delay, max_delay, jitter)
                        logger.warning(f"Retriable error in {func.__name__} (attempt {attempt + 1}/{max_attempts}): {e}. Retrying in {delay:.2f}s")
                        time.sleep(delay)
                    else:
                        logger.error(f"Max retries exceeded for {func.__name__}: {e}")
                        raise
                except Exception as e:
                    # Non-retriable exceptions
                    logger.error(f"Non-retriable exception in {func.__name__}: {e}")
                    raise
            
            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


class S3ClientManager:
    """Enhanced S3 client manager with connection pooling, circuit breaker, and health monitoring."""
    
    def __init__(self):
        self._client = None
        self._client_created_at = 0
        self._client_ttl = 300  # 5 minutes
        self._client_lock = threading.Lock()
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=getattr(settings, 's3_failure_threshold', 5),
            recovery_timeout=getattr(settings, 's3_recovery_timeout', 60),
            success_threshold=getattr(settings, 's3_success_threshold', 2)
        )
        self._health_cache = {}
        self._health_cache_ttl = 30
        self._last_health_check = 0
        self._operation_stats = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'avg_response_time': 0,
            'last_operation_time': 0
        }
        self._stats_lock = threading.Lock()
    
    def _create_client(self):
        """Create a new S3 client with optimized configuration."""
        try:
            config = Config(
                retries={
                    'max_attempts': 0,  # We handle retries ourselves with jitter
                    'mode': 'standard'
                },
                max_pool_connections=100,
                region_name=settings.aws_region,
                signature_version='s3v4',
                s3={
                    'addressing_style': 'virtual',
                    'use_accelerate_endpoint': False,
                    'payload_signing_enabled': True
                },
                connect_timeout=getattr(settings, 's3_connect_timeout', 30),
                read_timeout=getattr(settings, 's3_read_timeout', 60),
                retries_total_max_attempts=0,  # Disable built-in retries
                tcp_keepalive=True
            )
            
            if settings.use_aws:
                client = boto3.client('s3', config=config, region_name=settings.aws_region)
            else:
                client = boto3.client(
                    's3',
                    endpoint_url=settings.s3_endpoint,
                    aws_access_key_id=settings.aws_access_key_id,
                    aws_secret_access_key=settings.aws_secret_access_key,
                    region_name=settings.aws_region,
                    config=config
                )
            
            # Verify credentials and bucket access
            try:
                client.head_bucket(Bucket=settings.s3_bucket)
                logger.info("S3 client created and bucket access verified")
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    logger.warning(f"S3 bucket '{settings.s3_bucket}' not found")
                else:
                    logger.error(f"S3 bucket access error: {e}")
                    raise
            
            self._client = client
            self._client_created_at = time.time()
            return client
            
        except NoCredentialsError:
            logger.error("S3 credentials not found")
            raise
        except Exception as e:
            logger.error(f"Failed to create S3 client: {e}")
            raise
    
    def get_client(self):
        """Get S3 client, creating new one if needed or expired."""
        current_time = time.time()
        
        # Check without lock first (double-checked locking pattern)
        if (self._client and 
            current_time - self._client_created_at <= self._client_ttl):
            return self._client
        
        with self._client_lock:
            # Check again inside lock
            if (not self._client or 
                current_time - self._client_created_at > self._client_ttl):
                self._create_client()
        
        return self._client
    
    def _record_operation(self, success: bool, response_time: float, operation_name: str = None):
        """Record operation statistics thread-safely."""
        with self._stats_lock:
            self._operation_stats['total_operations'] += 1
            self._operation_stats['last_operation_time'] = time.time()
            
            if success:
                self._operation_stats['successful_operations'] += 1
                self._circuit_breaker.record_success()
            else:
                self._operation_stats['failed_operations'] += 1
                self._circuit_breaker.record_failure()
            
            # Update average response time
            total_ops = self._operation_stats['total_operations']
            current_avg = self._operation_stats['avg_response_time']
            self._operation_stats['avg_response_time'] = (
                (current_avg * (total_ops - 1) + response_time) / total_ops
            )
            
        # Log slow operations
        if response_time > 5.0:
            logger.warning(f"Slow S3 operation: {operation_name or 'unknown'} took {response_time:.2f}s")
    
    def execute_with_circuit_breaker(self, operation_name: str, operation_func: Callable[[], T], 
                                   idempotent: bool = True) -> T:
        """Execute S3 operation with circuit breaker protection and optional retry."""
        if not self._circuit_breaker.can_execute():
            raise Exception(f"S3 circuit breaker is open - {operation_name} operation blocked")
        
        start_time = time.time()
        
        # Wrap operation with retry logic if idempotent
        if idempotent:
            @retry_with_exponential_backoff(
                max_attempts=getattr(settings, 's3_max_retries', 3),
                base_delay=getattr(settings, 's3_retry_base_delay', 1.0),
                max_delay=getattr(settings, 's3_retry_max_delay', 30.0),
                jitter=getattr(settings, 's3_retry_jitter', 0.2)
            )
            def retryable_operation():
                return operation_func()
            
            operation_to_execute = retryable_operation
        else:
            operation_to_execute = operation_func
        
        try:
            result = operation_to_execute()
            response_time = time.time() - start_time
            self._record_operation(success=True, response_time=response_time, operation_name=operation_name)
            
            logger.debug(f"S3 {operation_name} completed in {response_time:.3f}s")
            return result
            
        except Exception as e:
            response_time = time.time() - start_time
            self._record_operation(success=False, response_time=response_time, operation_name=operation_name)
            
            logger.error(f"S3 {operation_name} failed after {response_time:.3f}s: {e}")
            raise
    
    def generate_presigned_url(self, key: str, content_type: str, file_size: int, expires_in: int = 900) -> str:
        """Generate presigned URL for S3 upload with circuit breaker protection."""
        # Validate inputs
        if not key or not isinstance(key, str):
            raise ValueError("S3 key must be a non-empty string")
        if expires_in <= 0 or expires_in > 604800:  # Max 7 days
            raise ValueError("Expires in must be between 1 and 604800 seconds")
        
        def operation():
            client = self.get_client()
            return client.generate_presigned_url(
                ClientMethod='put_object',
                Params={
                    'Bucket': settings.s3_bucket,
                    'Key': key,
                    'ContentType': content_type,
                    'ContentLength': file_size,
                    'ServerSideEncryption': 'AES256' if getattr(settings, 's3_server_side_encryption', True) else None
                },
                ExpiresIn=expires_in
            )
        
        return self.execute_with_circuit_breaker('generate_presigned_url', operation, idempotent=True)
    
    def download_file(self, key: str, max_size: Optional[int] = None) -> bytes:
        """Download file from S3 with circuit breaker protection and size limits."""
        if not key or not isinstance(key, str):
            raise ValueError("S3 key must be a non-empty string")
        
        def operation():
            client = self.get_client()
            
            # First check file size if max_size specified
            if max_size:
                try:
                    head_response = client.head_object(Bucket=settings.s3_bucket, Key=key)
                    file_size = head_response.get('ContentLength', 0)
                    if file_size > max_size:
                        raise ValueError(f"File size {file_size} exceeds maximum allowed size {max_size}")
                except ClientError as e:
                    if e.response['Error']['Code'] == '404':
                        raise FileNotFoundError(f"S3 object not found: {key}")
                    raise
            
            response = client.get_object(Bucket=settings.s3_bucket, Key=key)
            return response['Body'].read()
        
        return self.execute_with_circuit_breaker('download_file', operation, idempotent=True)
    
    def upload_file(self, key: str, data: bytes, content_type: str, metadata: Optional[Dict[str, str]] = None) -> None:
        """Upload file to S3 with circuit breaker protection and metadata support."""
        if not key or not isinstance(key, str):
            raise ValueError("S3 key must be a non-empty string")
        if not isinstance(data, bytes):
            raise TypeError("Data must be bytes")
        
        def operation():
            client = self.get_client()
            params = {
                'Bucket': settings.s3_bucket,
                'Key': key,
                'Body': data,
                'ContentType': content_type
            }
            
            # Add server-side encryption if configured
            if getattr(settings, 's3_server_side_encryption', True):
                params['ServerSideEncryption'] = 'AES256'
            
            # Add metadata if provided
            if metadata:
                # S3 metadata keys must be lowercase
                params['Metadata'] = {k.lower(): str(v) for k, v in metadata.items()}
            
            client.put_object(**params)
        
        # Uploads are not idempotent by default
        return self.execute_with_circuit_breaker('upload_file', operation, idempotent=False)
    
    def delete_file(self, key: str) -> None:
        """Delete file from S3 with circuit breaker protection."""
        if not key or not isinstance(key, str):
            raise ValueError("S3 key must be a non-empty string")
        
        def operation():
            client = self.get_client()
            # S3 delete is idempotent - returns success even if object doesn't exist
            client.delete_object(Bucket=settings.s3_bucket, Key=key)
        
        return self.execute_with_circuit_breaker('delete_file', operation, idempotent=True)
    
    def file_exists(self, key: str) -> bool:
        """Check if file exists in S3."""
        def operation():
            client = self.get_client()
            try:
                client.head_object(Bucket=settings.s3_bucket, Key=key)
                return True
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    return False
                raise
        
        return self.execute_with_circuit_breaker('file_exists', operation)
    
    def get_file_metadata(self, key: str) -> Dict[str, Any]:
        """Get file metadata from S3."""
        def operation():
            client = self.get_client()
            response = client.head_object(Bucket=settings.s3_bucket, Key=key)
            return {
                'size': response.get('ContentLength', 0),
                'last_modified': response.get('LastModified'),
                'content_type': response.get('ContentType'),
                'etag': response.get('ETag', '').strip('"')
            }
        
        return self.execute_with_circuit_breaker('get_file_metadata', operation)
    
    def health_check(self) -> Dict[str, Any]:
        """Comprehensive S3 health check with caching."""
        current_time = time.time()
        
        # Return cached result if still valid
        if (current_time - self._last_health_check < self._health_cache_ttl 
            and self._health_cache):
            return self._health_cache
        
        try:
            start_time = time.time()
            
            # Test basic connectivity and bucket access
            client = self.get_client()
            client.head_bucket(Bucket=settings.s3_bucket)
            
            # Test presigned URL generation
            test_key = f"health-check-{int(current_time)}.txt"
            presigned_url = client.generate_presigned_url(
                ClientMethod='put_object',
                Params={
                    'Bucket': settings.s3_bucket,
                    'Key': test_key,
                    'ContentType': 'text/plain'
                },
                ExpiresIn=60
            )
            
            health_time = time.time() - start_time
            
            health_info = {
                'status': 'healthy',
                'response_time_ms': round(health_time * 1000, 2),
                'circuit_breaker': self._circuit_breaker.get_status(),
                'operation_stats': self._operation_stats.copy(),
                'client_age_seconds': current_time - self._client_created_at,
                'bucket': settings.s3_bucket,
                'endpoint': settings.s3_endpoint if not settings.use_aws else 'AWS S3',
                'timestamp': current_time
            }
            
            # Cache the result
            self._health_cache = health_info
            self._last_health_check = current_time
            
            logger.debug(f"S3 health check completed in {health_time:.3f}s")
            return health_info
            
        except Exception as e:
            error_info = {
                'status': 'unhealthy',
                'error': str(e),
                'circuit_breaker': self._circuit_breaker.get_status(),
                'operation_stats': self._operation_stats.copy(),
                'timestamp': current_time
            }
            logger.error(f"S3 health check failed: {e}")
            return error_info
    
    def get_stats(self) -> Dict[str, Any]:
        """Get S3 client statistics."""
        return {
            'operation_stats': self._operation_stats.copy(),
            'circuit_breaker': self._circuit_breaker.get_status(),
            'client_age_seconds': time.time() - self._client_created_at,
            'client_ttl_seconds': self._client_ttl
        }
    
    def reset_stats(self):
        """Reset operation statistics."""
        with self._stats_lock:
            self._operation_stats = {
                'total_operations': 0,
                'successful_operations': 0,
                'failed_operations': 0,
                'avg_response_time': 0,
                'last_operation_time': 0
            }
        logger.info("S3 client statistics reset")
    
    def reset_circuit_breaker(self):
        """Reset circuit breaker to closed state."""
        with self._circuit_breaker._lock:
            self._circuit_breaker.state = 'closed'
            self._circuit_breaker.failure_count = 0
            self._circuit_breaker.success_count = 0
        logger.info("S3 circuit breaker reset to closed state")

# Global S3 client manager instance
s3_manager = S3ClientManager()

# Legacy compatibility functions
class S3ClientFactory:
    @staticmethod
    def create_client():
        return s3_manager.get_client()

def generate_presigned_url(key: str, content_type: str, file_size: int, expires_in: int = 900) -> str:
    return s3_manager.generate_presigned_url(key, content_type, file_size, expires_in)

def download_file(key: str) -> bytes:
    return s3_manager.download_file(key)

def upload_file(key: str, data: bytes, content_type: str) -> None:
    return s3_manager.upload_file(key, data, content_type)

def delete_file(key: str) -> None:
    return s3_manager.delete_file(key)

def file_exists(key: str) -> bool:
    return s3_manager.file_exists(key)

def get_file_metadata(key: str) -> Dict[str, Any]:
    return s3_manager.get_file_metadata(key)

def get_s3_health() -> Dict[str, Any]:
    return s3_manager.health_check()

def get_s3_stats() -> Dict[str, Any]:
    return s3_manager.get_stats()