import time
from collections import defaultdict
from typing import Dict, Tuple
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import asyncio

class InMemoryRateLimiter:
    """Simple in-memory rate limiter using token bucket algorithm."""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.clients: Dict[str, Tuple[float, int]] = defaultdict(lambda: (time.time(), max_requests))
        self.lock = asyncio.Lock()
    
    async def is_allowed(self, client_id: str) -> bool:
        """Check if request is allowed for client."""
        async with self.lock:
            now = time.time()
            last_refill, tokens = self.clients[client_id]
            
            # Calculate tokens to add based on elapsed time
            elapsed = now - last_refill
            tokens_to_add = int(elapsed * (self.max_requests / self.window_seconds))
            
            # Refill tokens (up to max)
            tokens = min(self.max_requests, tokens + tokens_to_add)
            
            # Check if request is allowed
            if tokens > 0:
                tokens -= 1
                self.clients[client_id] = (now, tokens)
                return True
            else:
                self.clients[client_id] = (last_refill, tokens)
                return False

# Global rate limiter instance
rate_limiter = InMemoryRateLimiter(max_requests=100, window_seconds=60)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware."""
    
    def __init__(self, app):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next):
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        
        # Check rate limit
        if not await rate_limiter.is_allowed(client_ip):
            return Response(
                content='{"error": {"code": 429, "message": "Too many requests"}}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "60"}
            )
        
        # Process request
        response = await call_next(request)
        return response