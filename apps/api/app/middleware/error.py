from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging

logger = logging.getLogger(__name__)

async def error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global error handler that returns consistent error envelope"""
    
    if isinstance(exc, HTTPException):
        # FastAPI HTTP exceptions
        status_code = exc.status_code
        error_code = get_error_code(status_code)
        message = exc.detail
    elif isinstance(exc, StarletteHTTPException):
        # Starlette HTTP exceptions
        status_code = exc.status_code
        error_code = get_error_code(status_code)
        message = exc.detail
    elif isinstance(exc, RequestValidationError):
        # Pydantic validation errors
        status_code = 422
        error_code = "VALIDATION_ERROR"
        message = "Request validation failed"
        # Add validation details
        details = []
        for error in exc.errors():
            details.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"]
            })
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": error_code,
                    "message": message,
                    "details": details
                }
            }
        )
    else:
        # Unexpected errors
        status_code = 500
        error_code = "INTERNAL_ERROR"
        message = "An unexpected error occurred"
        logger.exception(f"Unexpected error: {exc}")
    
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": error_code,
                "message": message
            }
        }
    )

def get_error_code(status_code: int) -> str:
    """Map HTTP status codes to error codes"""
    error_codes = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
    }
    return error_codes.get(status_code, "UNKNOWN_ERROR")