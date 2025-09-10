import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, AsyncGenerator
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from .settings import settings

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
            logger.warning(f"S3 circuit breaker opened after {self.failure_count} failures")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            'state': self.state,
            'failure_count': self.failure_count,
            'last_failure_time': self.last_failure_time,
            'failure_threshold': self.failure_threshold,
            'recovery_timeout': self.recovery_timeout
        }

class S3ClientManager:
    """Enhanced S3 client manager with connection pooling, circuit breaker, and health monitoring."""
    
    def __init__(self):
        self._client = None
        self._client_created_at = 0
        self._client_ttl = 300  # 5 minutes
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=getattr(settings, 's3_failure_threshold', 5),
            recovery_timeout=getattr(settings, 's3_recovery_timeout', 60)
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
    
    def _create_client(self):
        """Create a new S3 client with optimized configuration."""
        try:
            config = Config(
                retries={
                    'max_attempts': 3, 
                    'mode': 'adaptive',
                    'total_max_attempts': 5
                },
                max_pool_connections=100,
                region_name=settings.aws_region,
                signature_version='s3v4',
                s3={
                    'addressing_style': 'virtual'
                },
                connect_timeout=30,
                read_timeout=60,
                parameter_validation=False  # Slight performance improvement
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
        
        # Create new client if none exists or if TTL expired
        if (not self._client or 
            current_time - self._client_created_at > self._client_ttl):
            self._create_client()
        
        return self._client
    
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
    
    def execute_with_circuit_breaker(self, operation_name: str, operation_func):
        """Execute S3 operation with circuit breaker protection."""
        if not self._circuit_breaker.can_execute():
            raise Exception(f"S3 circuit breaker is open - {operation_name} operation blocked")
        
        start_time = time.time()
        try:
            result = operation_func()
            response_time = time.time() - start_time
            self._record_operation(success=True, response_time=response_time)
            
            logger.debug(f"S3 {operation_name} completed in {response_time:.3f}s")
            return result
            
        except Exception as e:
            response_time = time.time() - start_time
            self._record_operation(success=False, response_time=response_time)
            
            logger.error(f"S3 {operation_name} failed after {response_time:.3f}s: {e}")
            raise
    
    def generate_presigned_url(self, key: str, content_type: str, file_size: int, expires_in: int = 900) -> str:
        """Generate presigned URL for S3 upload with circuit breaker protection."""
        def operation():
            client = self.get_client()
            return client.generate_presigned_url(
                ClientMethod='put_object',
                Params={
                    'Bucket': settings.s3_bucket,
                    'Key': key,
                    'ContentType': content_type,
                    'ContentLength': file_size
                },
                ExpiresIn=expires_in
            )
        
        return self.execute_with_circuit_breaker('generate_presigned_url', operation)
    
    def download_file(self, key: str) -> bytes:
        """Download file from S3 with circuit breaker protection."""
        def operation():
            client = self.get_client()
            response = client.get_object(Bucket=settings.s3_bucket, Key=key)
            return response['Body'].read()
        
        return self.execute_with_circuit_breaker('download_file', operation)
    
    def upload_file(self, key: str, data: bytes, content_type: str) -> None:
        """Upload file to S3 with circuit breaker protection."""
        def operation():
            client = self.get_client()
            client.put_object(
                Bucket=settings.s3_bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                ServerSideEncryption='AES256' if settings.use_aws else None
            )
        
        return self.execute_with_circuit_breaker('upload_file', operation)
    
    def delete_file(self, key: str) -> None:
        """Delete file from S3 with circuit breaker protection."""
        def operation():
            client = self.get_client()
            client.delete_object(Bucket=settings.s3_bucket, Key=key)
        
        return self.execute_with_circuit_breaker('delete_file', operation)
    
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
        self._operation_stats = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'avg_response_time': 0,
            'last_operation_time': 0
        }
        logger.info("S3 client statistics reset")

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