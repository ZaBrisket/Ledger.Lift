"""Shared Redis connection helper for worker processes."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

import redis

from apps.worker.config import get_worker_settings

logger = logging.getLogger(__name__)


@lru_cache
def _get_pool() -> redis.ConnectionPool:
    settings = get_worker_settings()
    try:
        return redis.ConnectionPool.from_url(settings.redis_url, max_connections=64)
    except redis.RedisError as exc:  # pragma: no cover - configuration issue
        logger.exception("Unable to configure Redis pool: %s", exc)
        raise


def get_redis_connection(*, health_check_interval: Optional[int] = 30) -> redis.Redis:
    """Return a Redis client backed by a cached pool."""

    return redis.Redis(connection_pool=_get_pool(), health_check_interval=health_check_interval)


def reset_worker_redis_cache() -> None:
    """Reset connection pool cache (for testing)."""

    _get_pool.cache_clear()
