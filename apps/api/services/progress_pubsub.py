"""Redis pub/sub helpers for job progress streaming."""
from __future__ import annotations

import asyncio
import json
import math
import time
from typing import AsyncGenerator, Dict, Optional

from fastapi import Request
from fastapi.responses import StreamingResponse

from apps.api.app.progress import PROGRESS_CHANNEL, PROGRESS_KEY_TEMPLATE
from apps.api.config import settings
from apps.api.infra.redis import get_redis_connection

DURATION_KEY = "jobs:durations"
DURATION_WINDOW = 200
KEEPALIVE_INTERVAL = 15


def record_job_duration(duration_seconds: float, *, connection=None) -> None:
    """Persist job durations for adaptive fallback hints."""

    conn = connection or get_redis_connection()
    try:
        conn.lpush(DURATION_KEY, duration_seconds)
        conn.ltrim(DURATION_KEY, 0, DURATION_WINDOW - 1)
    except Exception:  # pragma: no cover - defensive logging happens at caller
        pass


def estimate_p95_ms(*, connection=None) -> int:
    """Estimate the p95 duration from stored samples (ms)."""

    conn = connection or get_redis_connection()
    try:
        raw_values = conn.lrange(DURATION_KEY, 0, DURATION_WINDOW - 1)
    except Exception:  # pragma: no cover - best effort
        raw_values = []

    durations = [float(value) for value in raw_values if value not in {None, b""}]
    if not durations:
        return min(settings.sse_edge_budget_ms, settings.parse_timeout_ms)

    sorted_values = sorted(durations)
    index = max(0, math.ceil(0.95 * len(sorted_values)) - 1)
    p95_seconds = sorted_values[index]
    estimate = int(p95_seconds * 1000)
    return min(estimate, settings.sse_edge_budget_ms)


def _format_event(event: str, payload: Dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


def _format_comment(message: str) -> str:
    return f": {message}\n\n"


def _deserialize_snapshot(raw) -> Optional[Dict[str, object]]:
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _initial_snapshot(job_id: str, *, connection=None) -> Optional[Dict[str, object]]:
    conn = connection or get_redis_connection()
    key = PROGRESS_KEY_TEMPLATE.format(job_id=job_id)
    raw = conn.get(key)
    return _deserialize_snapshot(raw)


async def stream_job_events(request: Request, job_id: str) -> StreamingResponse:
    """Create an SSE response for job progress events."""

    conn = get_redis_connection()
    pubsub = conn.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(PROGRESS_CHANNEL)
    p95_hint = estimate_p95_ms(connection=conn)

    async def event_iterator() -> AsyncGenerator[bytes, None]:
        last_keepalive = time.monotonic()
        initial = _initial_snapshot(job_id, connection=conn)
        if initial:
            yield _format_event("progress", initial).encode("utf-8")

        try:
            while True:
                if await request.is_disconnected():
                    break

                message = pubsub.get_message(ignore_subscribe_messages=True)
                if message and message.get("type") == "message":
                    data = _deserialize_snapshot(message.get("data"))
                    if data and data.get("job_id") == job_id:
                        yield _format_event("progress", data).encode("utf-8")
                        if "duration" in data:
                            try:
                                record_job_duration(float(data["duration"]), connection=conn)
                            except (TypeError, ValueError):
                                pass

                now = time.monotonic()
                if now - last_keepalive > KEEPALIVE_INTERVAL:
                    yield _format_comment("keep-alive").encode("utf-8")
                    last_keepalive = now

                await asyncio.sleep(0.25)
        finally:
            pubsub.close()

    headers = {
        "Cache-Control": "no-store",
        "X-P95-JOB-MS": str(p95_hint),
    }
    return StreamingResponse(event_iterator(), media_type="text/event-stream", headers=headers)


__all__ = [
    "stream_job_events",
    "estimate_p95_ms",
    "record_job_duration",
]
