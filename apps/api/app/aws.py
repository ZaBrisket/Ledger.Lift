import os
import time
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from functools import wraps
from contextlib import asynccontextmanager

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError, ConnectionError as BotoConnectionError
from boto3.s3.transfer import TransferConfig

from .settings import settings

logger = logging.getLogger(__name__)

# Configuration
S3_FAILURE_THRESHOLD = int(os.getenv('S3_FAILURE_THRESHOLD', '5'))
S3_RECOVERY_TIMEOUT = int(os.getenv('S3_RECOVERY_TIMEOUT', '60'))  # seconds
S3_CLIENT_REFRESH_INTERVAL = int(os.getenv('S3_CLIENT_REFRESH_INTERVAL', '300'))  # 5 minutes
S3_MAX_RETRIES = int(os.getenv('S3_MAX_RETRIES', '3'))
S3_CONNECTION_TIMEOUT = int(os.getenv('S3_CONNECTION_TIMEOUT', '10'))
S3_READ_TIMEOUT = int(os.getenv('S3_READ_TIMEOUT', '30'))

class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open"""
    pass

class S3CircuitBreaker:
    """Circuit breaker implementation for S3 operations"""
    
    def __init__(self, failure_threshold: int = S3_FAILURE_THRESHOLD, 
                 recovery_timeout: int = S3_RECOVERY_TIMEOUT):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'closed'  # closed, open, half-open
        self._lock = asyncio.Lock()
    
    async def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        async with self._lock:
            if self.state == 'open':
                if self._should_attempt_reset():
                    self.state = 'half-open'
                    logger.info("Circuit breaker entering half-open state")
                else:
                    raise CircuitBreakerError(
                        f"Circuit breaker is open. Retry after {self.recovery_timeout}s"
                    )
        
        try:
            # Execute the function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, func, *args, **kwargs
                )
            
            # Success - reset on half-open
            async with self._lock:
                if self.state == 'half-open':
                    self.state = 'closed'
                    self.failure_count = 0
                    logger.info("Circuit breaker closed after successful operation")
            
            return result
            
        except Exception as e:
            # Record failure
            async with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                if self.failure_count >= self.failure_threshold:
                    self.state = 'open'
                    logger.error(f"Circuit breaker opened after {self.failure_count} failures")
                
                logger.warning(f"S3 operation failed ({self.failure_count}/{self.failure_threshold}): {str(e)}")
            
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        return (self.last_failure_time and 
                time.time() - self.last_failure_time >= self.recovery_timeout)
    
    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state"""
        return {
            'state': self.state,
            'failure_count': self.failure_count,
            'failure_threshold': self.failure_threshold,
            'last_failure_time': self.last_failure_time,
            'recovery_timeout': self.recovery_timeout
        }

class EnhancedS3Client:
    """Enhanced S3 client with connection pooling, circuit breaker, and retry logic"""
    
    def __init__(self):
        self._client = None
        self._client_created_at = None
        self._circuit_breaker = S3CircuitBreaker()
        self._transfer_config = TransferConfig(
            multipart_threshold=1024 * 25,  # 25MB
            max_concurrency=10,
            multipart_chunksize=1024 * 25,
            use_threads=True
        )
        self._client_lock = asyncio.Lock()
    
    async def _get_client(self):
        """Get or create S3 client with automatic refresh"""
        async with self._client_lock:
            now = datetime.utcnow()
            
            # Create new client if needed
            if (self._client is None or 
                self._client_created_at is None or
                (now - self._client_created_at).seconds > S3_CLIENT_REFRESH_INTERVAL):
                
                logger.info("Creating new S3 client")
                
                config = Config(
                    retries={
                        'max_attempts': S3_MAX_RETRIES,
                        'mode': 'adaptive'
                    },
                    max_pool_connections=50,
                    connect_timeout=S3_CONNECTION_TIMEOUT,
                    read_timeout=S3_READ_TIMEOUT,
                    tcp_keepalive=True
                )
                
                if settings.use_aws:
                    self._client = boto3.client(
                        's3',
                        config=config,
                        region_name=settings.aws_region
                    )
                else:
                    self._client = boto3.client(
                        's3',
                        endpoint_url=settings.s3_endpoint,
                        aws_access_key_id=settings.aws_access_key_id,
                        aws_secret_access_key=settings.aws_secret_access_key,
                        region_name=settings.aws_region,
                        config=config
                    )
                
                self._client_created_at = now
                
                # Test the connection
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        self._client.head_bucket,
                        Bucket=settings.s3_bucket
                    )
                    logger.info("S3 client connection verified")
                except Exception as e:
                    logger.error(f"Failed to verify S3 connection: {str(e)}")
                    self._client = None
                    raise
            
            return self._client
    
    async def generate_presigned_url(
        self,
        key: str,
        content_type: str,
        file_size: int,
        expires_in: int = 900,
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """Generate presigned URL for upload with circuit breaker protection"""
        
        async def _generate():
            client = await self._get_client()
            
            params = {
                'Bucket': settings.s3_bucket,
                'Key': key,
                'ContentType': content_type,
                'ContentLength': file_size
            }
            
            if metadata:
                params['Metadata'] = metadata
            
            return client.generate_presigned_url(
                ClientMethod='put_object',
                Params=params,
                ExpiresIn=expires_in
            )
        
        return await self._circuit_breaker.call(_generate)
    
    async def generate_presigned_post(
        self,
        key: str,
        content_type: str,
        file_size: int,
        expires_in: int = 900,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Generate presigned POST data for multipart upload"""
        
        async def _generate():
            client = await self._get_client()
            
            conditions = [
                ['content-length-range', 0, file_size + 1024],  # Allow small overhead
                {'Content-Type': content_type}
            ]
            
            fields = {'Content-Type': content_type}
            if metadata:
                fields.update({f'x-amz-meta-{k}': v for k, v in metadata.items()})
            
            return client.generate_presigned_post(
                Bucket=settings.s3_bucket,
                Key=key,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=expires_in
            )
        
        return await self._circuit_breaker.call(_generate)
    
    async def download_file(self, key: str) -> bytes:
        """Download file from S3 with circuit breaker protection"""
        
        async def _download():
            client = await self._get_client()
            response = client.get_object(Bucket=settings.s3_bucket, Key=key)
            return response['Body'].read()
        
        return await self._circuit_breaker.call(_download)
    
    async def download_file_stream(self, key: str, chunk_size: int = 8192):
        """Download file as async stream"""
        
        async def _get_object():
            client = await self._get_client()
            return client.get_object(Bucket=settings.s3_bucket, Key=key)
        
        response = await self._circuit_breaker.call(_get_object)
        
        # Stream the body
        body = response['Body']
        try:
            while True:
                chunk = await asyncio.get_event_loop().run_in_executor(
                    None, body.read, chunk_size
                )
                if not chunk:
                    break
                yield chunk
        finally:
            body.close()
    
    async def upload_file(
        self,
        key: str,
        data: bytes,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None
    ) -> None:
        """Upload file to S3 with circuit breaker protection"""
        
        async def _upload():
            client = await self._get_client()
            
            kwargs = {
                'Bucket': settings.s3_bucket,
                'Key': key,
                'Body': data,
                'ContentType': content_type
            }
            
            if metadata:
                kwargs['Metadata'] = metadata
            
            client.put_object(**kwargs)
        
        await self._circuit_breaker.call(_upload)
    
    async def upload_file_multipart(
        self,
        key: str,
        file_path: str,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None,
        progress_callback: Optional[callable] = None
    ) -> None:
        """Upload large file using multipart upload"""
        
        async def _upload():
            client = await self._get_client()
            
            extra_args = {'ContentType': content_type}
            if metadata:
                extra_args['Metadata'] = metadata
            
            # Use transfer manager for large files
            client.upload_file(
                file_path,
                settings.s3_bucket,
                key,
                ExtraArgs=extra_args,
                Config=self._transfer_config,
                Callback=progress_callback
            )
        
        await self._circuit_breaker.call(_upload)
    
    async def delete_file(self, key: str) -> None:
        """Delete file from S3"""
        
        async def _delete():
            client = await self._get_client()
            client.delete_object(Bucket=settings.s3_bucket, Key=key)
        
        await self._circuit_breaker.call(_delete)
    
    async def file_exists(self, key: str) -> bool:
        """Check if file exists in S3"""
        
        async def _check():
            client = await self._get_client()
            try:
                client.head_object(Bucket=settings.s3_bucket, Key=key)
                return True
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    return False
                raise
        
        return await self._circuit_breaker.call(_check)
    
    async def get_file_metadata(self, key: str) -> Dict[str, Any]:
        """Get file metadata from S3"""
        
        async def _get_metadata():
            client = await self._get_client()
            response = client.head_object(Bucket=settings.s3_bucket, Key=key)
            
            return {
                'size': response.get('ContentLength', 0),
                'content_type': response.get('ContentType', ''),
                'last_modified': response.get('LastModified'),
                'etag': response.get('ETag', '').strip('"'),
                'metadata': response.get('Metadata', {})
            }
        
        return await self._circuit_breaker.call(_get_metadata)
    
    async def list_files(
        self,
        prefix: str = '',
        max_keys: int = 1000,
        continuation_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """List files in S3 bucket"""
        
        async def _list():
            client = await self._get_client()
            
            kwargs = {
                'Bucket': settings.s3_bucket,
                'MaxKeys': max_keys
            }
            
            if prefix:
                kwargs['Prefix'] = prefix
            
            if continuation_token:
                kwargs['ContinuationToken'] = continuation_token
            
            return client.list_objects_v2(**kwargs)
        
        return await self._circuit_breaker.call(_list)
    
    def get_health(self) -> Dict[str, Any]:
        """Get S3 client health status"""
        circuit_state = self._circuit_breaker.get_state()
        
        return {
            'healthy': circuit_state['state'] != 'open',
            'circuit_breaker': circuit_state,
            'client_age': (
                (datetime.utcnow() - self._client_created_at).seconds 
                if self._client_created_at else None
            ),
            'client_refresh_interval': S3_CLIENT_REFRESH_INTERVAL
        }

# Create global instance
s3_client = EnhancedS3Client()

# Legacy function wrappers for backward compatibility
async def generate_presigned_url(key: str, content_type: str, file_size: int, expires_in: int = 900) -> str:
    """Legacy wrapper for presigned URL generation"""
    return await s3_client.generate_presigned_url(key, content_type, file_size, expires_in)

async def download_file(key: str) -> bytes:
    """Legacy wrapper for file download"""
    return await s3_client.download_file(key)

async def upload_file(key: str, data: bytes, content_type: str) -> None:
    """Legacy wrapper for file upload"""
    await s3_client.upload_file(key, data, content_type)

# Synchronous wrappers for non-async code
def generate_presigned_url_sync(key: str, content_type: str, file_size: int, expires_in: int = 900) -> str:
    """Synchronous wrapper for presigned URL generation"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            s3_client.generate_presigned_url(key, content_type, file_size, expires_in)
        )
    finally:
        loop.close()

def download_file_sync(key: str) -> bytes:
    """Synchronous wrapper for file download"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(s3_client.download_file(key))
    finally:
        loop.close()

def upload_file_sync(key: str, data: bytes, content_type: str) -> None:
    """Synchronous wrapper for file upload"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(s3_client.upload_file(key, data, content_type))
    finally:
        loop.close()

# Export all functions
__all__ = [
    's3_client',
    'generate_presigned_url',
    'download_file',
    'upload_file',
    'generate_presigned_url_sync',
    'download_file_sync',
    'upload_file_sync',
    'EnhancedS3Client',
    'S3CircuitBreaker',
    'CircuitBreakerError'
]