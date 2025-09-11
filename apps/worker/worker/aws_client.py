"""
Enhanced S3 client for worker with circuit breaker, retries, timeouts, and comprehensive error handling.
"""
import os
import logging
import time
from contextlib import contextmanager
from typing import Optional, Dict, Any
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

logger = logging.getLogger(__name__)

class CircuitBreaker:
    """Circuit breaker for S3 operations to prevent cascade failures."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = 'closed'  # closed, open, half-open
    
    def can_execute(self) -> bool:
        """Check if operation can be executed based on circuit breaker state."""
        if self.state == 'closed':
            return True
        elif self.state == 'open':
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = 'half-open'
                return True
            return False
        else:  # half-open
            return True
    
    def record_success(self):
        """Record successful operation."""
        self.failure_count = 0
        self.state = 'closed'
    
    def record_failure(self):
        """Record failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = 'open'
            logger.warning(f"Worker S3 circuit breaker opened after {self.failure_count} failures")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            'state': self.state,
            'failure_count': self.failure_count,
            'last_failure_time': self.last_failure_time,
            'failure_threshold': self.failure_threshold,
            'recovery_timeout': self.recovery_timeout
        }

class WorkerS3Client:
    """Enhanced S3 client for worker with circuit breaker, retries, and health monitoring."""
    
    def __init__(self):
        self.use_aws = os.getenv('USE_AWS', 'false').lower() == 'true'
        self.s3_endpoint = os.getenv('S3_ENDPOINT', 'http://localhost:9000')
        self.s3_bucket = os.getenv('S3_BUCKET', 'ledger-lift')
        self.aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID', 'minioadmin')
        self.aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY', 'minioadmin')
        self.aws_region = os.getenv('AWS_REGION', 'us-east-1')
        
        # Circuit breaker for failure protection
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=int(os.getenv('S3_FAILURE_THRESHOLD', '5')),
            recovery_timeout=int(os.getenv('S3_RECOVERY_TIMEOUT', '60'))
        )
        
        # Operation statistics
        self._operation_stats = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'avg_response_time': 0,
            'last_operation_time': 0
        }
        
        # Enhanced configuration with timeouts and retries
        config = Config(
            retries={
                'max_attempts': 3,
                'mode': 'adaptive',
                'total_max_attempts': 5
            },
            max_pool_connections=50,
            region_name=self.aws_region,
            connect_timeout=30,
            read_timeout=60,
            parameter_validation=False
        )
        
        try:
            if self.use_aws:
                self.client = boto3.client('s3', config=config, region_name=self.aws_region)
            else:
                self.client = boto3.client(
                    's3',
                    endpoint_url=self.s3_endpoint,
                    aws_access_key_id=self.aws_access_key_id,
                    aws_secret_access_key=self.aws_secret_access_key,
                    region_name=self.aws_region,
                    config=config
                )
            
            # Verify bucket access during initialization
            self._verify_bucket_access()
            logger.info("Worker S3 client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Worker S3 client: {e}")
            raise
    
    def _verify_bucket_access(self):
        """Verify bucket access during initialization."""
        try:
            self.client.head_bucket(Bucket=self.s3_bucket)
            logger.debug(f"Verified access to S3 bucket: {self.s3_bucket}")
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.warning(f"S3 bucket '{self.s3_bucket}' not found")
            else:
                logger.error(f"S3 bucket access error: {e}")
                raise
    
    def _record_operation(self, success: bool, response_time: float):
        """Record operation statistics."""
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
    
    def _execute_with_circuit_breaker(self, operation_name: str, operation_func):
        """Execute S3 operation with circuit breaker protection."""
        if not self._circuit_breaker.can_execute():
            raise Exception(f"S3 circuit breaker is open - {operation_name} operation blocked")
        
        start_time = time.time()
        try:
            result = operation_func()
            response_time = time.time() - start_time
            self._record_operation(success=True, response_time=response_time)
            
            logger.debug(f"Worker S3 {operation_name} completed in {response_time:.3f}s")
            return result
            
        except Exception as e:
            response_time = time.time() - start_time
            self._record_operation(success=False, response_time=response_time)
            
            logger.error(f"Worker S3 {operation_name} failed after {response_time:.3f}s: {e}")
            raise
    
    @contextmanager
    def _retry_on_failure(self, max_retries: int = 3, backoff_factor: float = 1.0):
        """Context manager for retrying operations with exponential backoff."""
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                yield attempt
                return  # Success, exit retry loop
            except (BotoCoreError, ClientError) as e:
                last_exception = e
                if attempt < max_retries - 1:
                    sleep_time = backoff_factor * (2 ** attempt)
                    logger.warning(f"S3 operation failed (attempt {attempt + 1}/{max_retries}), retrying in {sleep_time}s: {e}")
                    time.sleep(sleep_time)
                    continue
                break
            except Exception as e:
                # Don't retry on non-S3 errors
                logger.error(f"Non-retryable error in S3 operation: {e}")
                raise
        
        logger.error(f"S3 operation failed after {max_retries} attempts")
        raise last_exception

    def download_file(self, key: str) -> bytes:
        """Download file from S3 with circuit breaker and retry protection."""
        if not key or not key.strip():
            raise ValueError("S3 key cannot be empty")
        
        def operation():
            with self._retry_on_failure(max_retries=3, backoff_factor=1.0):
                response = self.client.get_object(Bucket=self.s3_bucket, Key=key.strip())
                return response['Body'].read()
        
        return self._execute_with_circuit_breaker('download_file', operation)
    
    def upload_file(self, key: str, data: bytes, content_type: str) -> None:
        """Upload file to S3 with circuit breaker and retry protection."""
        if not key or not key.strip():
            raise ValueError("S3 key cannot be empty")
        if not data:
            raise ValueError("Data cannot be empty")
        if not content_type or not content_type.strip():
            raise ValueError("Content type cannot be empty")
        
        def operation():
            with self._retry_on_failure(max_retries=3, backoff_factor=1.0):
                self.client.put_object(
                    Bucket=self.s3_bucket,
                    Key=key.strip(),
                    Body=data,
                    ContentType=content_type.strip(),
                    ServerSideEncryption='AES256' if self.use_aws else None
                )
        
        return self._execute_with_circuit_breaker('upload_file', operation)
    
    def file_exists(self, key: str) -> bool:
        """Check if file exists in S3."""
        if not key or not key.strip():
            raise ValueError("S3 key cannot be empty")
        
        def operation():
            with self._retry_on_failure(max_retries=2, backoff_factor=0.5):
                try:
                    self.client.head_object(Bucket=self.s3_bucket, Key=key.strip())
                    return True
                except ClientError as e:
                    if e.response['Error']['Code'] == '404':
                        return False
                    raise
        
        return self._execute_with_circuit_breaker('file_exists', operation)
    
    def get_file_metadata(self, key: str) -> Dict[str, Any]:
        """Get file metadata from S3."""
        if not key or not key.strip():
            raise ValueError("S3 key cannot be empty")
        
        def operation():
            with self._retry_on_failure(max_retries=2, backoff_factor=0.5):
                response = self.client.head_object(Bucket=self.s3_bucket, Key=key.strip())
                return {
                    'size': response.get('ContentLength', 0),
                    'last_modified': response.get('LastModified'),
                    'content_type': response.get('ContentType'),
                    'etag': response.get('ETag', '').strip('"')
                }
        
        return self._execute_with_circuit_breaker('get_file_metadata', operation)
    
    def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check for worker S3 client."""
        try:
            start_time = time.time()
            
            # Test basic connectivity and bucket access
            self.client.head_bucket(Bucket=self.s3_bucket)
            
            health_time = time.time() - start_time
            
            return {
                'status': 'healthy',
                'response_time_ms': round(health_time * 1000, 2),
                'circuit_breaker': self._circuit_breaker.get_status(),
                'operation_stats': self._operation_stats.copy(),
                'bucket': self.s3_bucket,
                'endpoint': self.s3_endpoint if not self.use_aws else 'AWS S3',
                'timestamp': time.time()
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'circuit_breaker': self._circuit_breaker.get_status(),
                'operation_stats': self._operation_stats.copy(),
                'timestamp': time.time()
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get S3 client statistics."""
        return {
            'operation_stats': self._operation_stats.copy(),
            'circuit_breaker': self._circuit_breaker.get_status()
        }
    
    def reset_stats(self):
        """Reset operation statistics."""
        self._operation_stats = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'avg_response_time': 0,
            'last_operation_time': 0
        }
        logger.info("Worker S3 client statistics reset")