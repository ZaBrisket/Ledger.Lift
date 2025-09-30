"""Shared Redis connection utilities for the API service."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

import redis

from apps.api.config import get_api_settings

logger = logging.getLogger(__name__)


class RedisConnectionError(RuntimeError):
    """Raised when the API is unable to create a Redis connection."""


@lru_cache
def _get_connection_pool() -> redis.ConnectionPool:
    settings = get_api_settings()
    try:
        return redis.ConnectionPool.from_url(settings.redis_url, max_connections=32)
    except redis.RedisError as exc:  # pragma: no cover - configuration issue
        logger.exception("Failed to create Redis connection pool: %s", exc)
        raise RedisConnectionError(str(exc)) from exc


def get_redis_connection(*, health_check_interval: Optional[int] = 30) -> redis.Redis:
    """Return a Redis client backed by a shared connection pool."""

    pool = _get_connection_pool()
    client = redis.Redis(connection_pool=pool, health_check_interval=health_check_interval)
    return client


def reset_redis_cache() -> None:
    """Reset cached pools (used in tests)."""

    _get_connection_pool.cache_clear()
