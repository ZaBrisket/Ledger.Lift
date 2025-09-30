"""API level configuration helpers for queueing and observability."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class APISettings(BaseSettings):
    """Environment driven settings for queue orchestration."""

    features_t1_queue: bool = True
    redis_url: str = "redis://localhost:6379/0"
    rq_default_queue: str = "default"
    rq_high_queue: str = "high"
    rq_low_queue: str = "low"
    rq_dead_queue: str = "dead"
    redis_max_retries: int = 3
    work_version: int = 1
    schema_version: int = 1
    parse_timeout_ms: int = 300000
    metrics_auth: Optional[str] = None

    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False


@lru_cache
def get_api_settings() -> APISettings:
    """Return cached API settings."""

    return APISettings()


def reset_api_settings_cache() -> None:
    """Clear cached settings (useful for tests)."""

    get_api_settings.cache_clear()
