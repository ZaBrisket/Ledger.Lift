import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from .settings import CORS_ALLOWED_ORIGINS, settings
from .routes import health, uploads, documents, artifacts
from .middleware.error import http_exception_handler, validation_exception_handler, general_exception_handler
from .middleware.ratelimit import RateLimitMiddleware
from .telemetry import init_telemetry, instrument_app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize OpenTelemetry
init_telemetry()

app = FastAPI(title="Ledger Lift API", version="0.1.0")

# Instrument the app with OpenTelemetry
instrument_app(app)

# Log adapter configuration on startup
@app.on_event("startup")
async def startup_event():
    adapter_type = "AWS" if settings.use_aws else "MinIO"
    logger.info(f"Using {adapter_type} adapter for S3 storage (USE_AWS={settings.use_aws})")
    logger.info(f"SQS queue configured: {settings.sqs_queue_name}")

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add exception handlers
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

app.include_router(health.router)
app.include_router(uploads.router)
app.include_router(documents.router)
app.include_router(artifacts.router)
