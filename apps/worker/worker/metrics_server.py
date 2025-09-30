from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from apps.worker.config import get_worker_settings

metrics_app = FastAPI(title="Ledger Lift Worker Metrics")
security = HTTPBasic(auto_error=False)


@metrics_app.get("/metrics")
def metrics(credentials: HTTPBasicCredentials | None = Depends(security)) -> Response:
    settings = get_worker_settings()
    if settings.metrics_auth:
        if credentials is None:
            raise HTTPException(
                status_code=401,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Basic"},
            )

        expected_user, _, expected_password = settings.metrics_auth.partition(":")
        if (
            credentials.username != expected_user
            or credentials.password != expected_password
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
