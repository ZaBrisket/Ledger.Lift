from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .settings import CORS_ALLOWED_ORIGINS
from .routes import health, uploads, documents, processing
from .middleware import MetricsMiddleware, RequestIDMiddleware, LoggingMiddleware
from .metrics import get_metrics_collector

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Ledger Lift API", version="0.1.0")

# Add rate limiting error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add custom middleware
app.add_middleware(LoggingMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(MetricsMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add metrics endpoint
@app.get("/metrics")
def get_metrics():
    """Prometheus metrics endpoint."""
    return get_metrics_collector().get_metrics_response()

app.include_router(health.router)
app.include_router(uploads.router)
app.include_router(documents.router)
app.include_router(processing.router)
