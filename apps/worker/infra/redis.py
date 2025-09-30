"""Redis connection utilities for the worker service."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

import redis

from apps.worker.config import get_settings


@lru_cache
def get_redis_connection(url: Optional[str] = None) -> redis.Redis:
    """Return a Redis client configured for the worker."""

    settings = get_settings()
    redis_url = url or settings.redis_url
    return redis.Redis.from_url(redis_url, retry_on_timeout=True)


def is_emergency_stopped(conn: Optional[redis.Redis] = None) -> bool:
    """Check whether the emergency stop flag is set."""

    from apps.worker.config import settings as worker_settings

    connection = conn or get_redis_connection()
    return bool(connection.exists(worker_settings.emergency_stop_key))
