from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .settings import CORS_ALLOWED_ORIGINS
from .routes import health, uploads, documents, artifacts
from .telemetry import setup_telemetry, instrument_app
from .middleware.error import error_handler
from .middleware.ratelimit import RateLimitMiddleware

app = FastAPI(title="Ledger Lift API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware, requests_per_minute=100)

app.include_router(health.router)
app.include_router(uploads.router)
app.include_router(documents.router)
app.include_router(artifacts.router)

# Setup OpenTelemetry
telemetry_metrics = setup_telemetry()
instrument_app(app)

# Add error handlers
app.add_exception_handler(StarletteHTTPException, error_handler)
app.add_exception_handler(RequestValidationError, error_handler)
app.add_exception_handler(Exception, error_handler)
