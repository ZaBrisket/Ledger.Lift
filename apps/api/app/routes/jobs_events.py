"""Streaming job progress events via SSE."""
from fastapi import APIRouter, HTTPException, Request

from apps.api.config import settings
from apps.api.services.progress_pubsub import stream_job_events

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs/{job_id}/events")
async def job_events(request: Request, job_id: str):
    if not settings.features_t1_sse:
        raise HTTPException(status_code=404, detail="SSE disabled")
    if not job_id or not job_id.strip():
        raise HTTPException(status_code=400, detail="job_id required")

    return await stream_job_events(request, job_id.strip())
