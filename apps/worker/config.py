"""Worker side configuration values."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class WorkerSettings(BaseSettings):
    """Environment driven settings for worker orchestration."""

    redis_url: str = "redis://localhost:6379/0"
    rq_default_queue: str = "default"
    rq_high_queue: str = "high"
    rq_low_queue: str = "low"
    rq_dead_queue: str = "dead"
    redis_max_retries: int = 3
    worker_concurrency: int = 2
    features_t1_queue: bool = True
    work_version: int = 1
    schema_version: int = 1
    parse_timeout_ms: int = 300000
    metrics_auth: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()


def reset_worker_settings_cache() -> None:
    get_worker_settings.cache_clear()
