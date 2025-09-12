"""
Custom middleware for metrics collection and request tracking.
"""
import time
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from .metrics import get_metrics_collector

logger = logging.getLogger(__name__)

class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect request metrics."""
    
    def __init__(self, app):
        super().__init__(app)
        self.metrics = get_metrics_collector()
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and collect metrics."""
        start_time = time.time()
        
        # Extract endpoint name from path
        endpoint = self._extract_endpoint(request.url.path)
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Record metrics
            self.metrics.record_request(
                method=request.method,
                endpoint=endpoint,
                status_code=response.status_code,
                duration=duration
            )
            
            return response
            
        except Exception as e:
            # Calculate duration even for errors
            duration = time.time() - start_time
            
            # Record error metrics
            self.metrics.record_error(
                error_type=type(e).__name__,
                component='api'
            )
            
            # Record request metrics for error
            self.metrics.record_request(
                method=request.method,
                endpoint=endpoint,
                status_code=500,
                duration=duration
            )
            
            raise
    
    def _extract_endpoint(self, path: str) -> str:
        """Extract endpoint name from path for metrics."""
        # Remove query parameters
        if '?' in path:
            path = path.split('?')[0]
        
        # Normalize common patterns
        if path.startswith('/v1/'):
            # Extract the main endpoint (e.g., /v1/documents/{id} -> /v1/documents/{id})
            parts = path.split('/')
            if len(parts) >= 3:
                # Keep the first 3 parts (e.g., /v1/documents)
                return '/'.join(parts[:3])
        
        return path

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID to all requests."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add request ID to request and response."""
        import uuid
        
        # Generate or extract request ID
        request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
        
        # Add to request state
        request.state.request_id = request_id
        
        # Process request
        response = await call_next(request)
        
        # Add request ID to response headers
        response.headers['X-Request-ID'] = request_id
        
        return response

class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for structured request logging."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response details."""
        start_time = time.time()
        request_id = getattr(request.state, 'request_id', 'unknown')
        
        # Log request
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                'request_id': request_id,
                'method': request.method,
                'path': request.url.path,
                'query_params': str(request.query_params),
                'client_ip': request.client.host if request.client else None,
                'user_agent': request.headers.get('user-agent'),
                'content_type': request.headers.get('content-type'),
                'content_length': request.headers.get('content-length')
            }
        )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Log response
            logger.info(
                f"Request completed: {request.method} {request.url.path} -> {response.status_code}",
                extra={
                    'request_id': request_id,
                    'method': request.method,
                    'path': request.url.path,
                    'status_code': response.status_code,
                    'duration_ms': round(duration * 1000, 2),
                    'response_size': response.headers.get('content-length')
                }
            )
            
            return response
            
        except Exception as e:
            # Calculate duration even for errors
            duration = time.time() - start_time
            
            # Log error
            logger.error(
                f"Request failed: {request.method} {request.url.path} -> {type(e).__name__}",
                extra={
                    'request_id': request_id,
                    'method': request.method,
                    'path': request.url.path,
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'duration_ms': round(duration * 1000, 2)
                },
                exc_info=True
            )
            
            raise