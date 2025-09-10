from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter (replace with Redis in production)"""
    
    def __init__(self, app, requests_per_minute: int = 100):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests: Dict[str, list] = {}
        self.cleanup_interval = 60  # Clean up old entries every 60 seconds
        self.last_cleanup = time.time()
    
    async def dispatch(self, request: Request, call_next):
        # Get client IP
        client_ip = self.get_client_ip(request)
        current_time = time.time()
        
        # Clean up old entries periodically
        if current_time - self.last_cleanup > self.cleanup_interval:
            self.cleanup_old_entries(current_time)
            self.last_cleanup = current_time
        
        # Check rate limit
        if not self.is_allowed(client_ip, current_time):
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute."
                    }
                },
                headers={"Retry-After": "60"}
            )
        
        # Record this request
        self.record_request(client_ip, current_time)
        
        # Process request
        response = await call_next(request)
        return response
    
    def get_client_ip(self, request: Request) -> str:
        """Get client IP address, considering proxy headers"""
        # Check for forwarded IP first
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        # Check for real IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fall back to direct connection
        return request.client.host if request.client else "unknown"
    
    def is_allowed(self, client_ip: str, current_time: float) -> bool:
        """Check if request is allowed based on rate limit"""
        if client_ip not in self.requests:
            return True
        
        # Remove requests older than 1 minute
        cutoff_time = current_time - 60
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip] 
            if req_time > cutoff_time
        ]
        
        # Check if under limit
        return len(self.requests[client_ip]) < self.requests_per_minute
    
    def record_request(self, client_ip: str, current_time: float):
        """Record a request for rate limiting"""
        if client_ip not in self.requests:
            self.requests[client_ip] = []
        self.requests[client_ip].append(current_time)
    
    def cleanup_old_entries(self, current_time: float):
        """Clean up old entries to prevent memory leaks"""
        cutoff_time = current_time - 60
        for client_ip in list(self.requests.keys()):
            self.requests[client_ip] = [
                req_time for req_time in self.requests[client_ip] 
                if req_time > cutoff_time
            ]
            # Remove empty entries
            if not self.requests[client_ip]:
                del self.requests[client_ip]