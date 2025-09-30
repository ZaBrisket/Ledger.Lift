"""FastAPI application exposing worker metrics."""
from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from apps.worker.config import settings

app = FastAPI(title="Ledger Lift Worker Monitor", version="0.1.0")
basic_auth = HTTPBasic(auto_error=False)


@app.get("/metrics")
def metrics(credentials: HTTPBasicCredentials = Depends(basic_auth)) -> Response:
    """Expose Prometheus metrics with optional basic auth."""

    if settings.metrics_auth:
        if not credentials:
            raise HTTPException(
                status_code=401,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Basic"},
            )
        try:
            expected_user, expected_pass = settings.metrics_auth.split(":", 1)
        except ValueError as exc:  # pragma: no cover - misconfiguration guard
            raise HTTPException(
                status_code=500,
                detail="Metrics authentication misconfigured",
            ) from exc
        if credentials.username != expected_user or credentials.password != expected_pass:
            raise HTTPException(
                status_code=401,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
