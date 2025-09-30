"""Worker configuration for queue processing and observability."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class WorkerConfig(BaseSettings):
    """Settings for the worker process."""

    redis_url: str = "redis://localhost:6379/0"
    rq_default_queue: str = "default"
    rq_high_queue: str = "high"
    rq_low_queue: str = "low"
    rq_dlq: str = "dead"
    worker_concurrency: int = 2
    redis_max_retries: int = 3
    parse_timeout_ms: int = 300_000
    metrics_auth: Optional[str] = None
    emergency_stop_key: str = "EMERGENCY_STOP"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        fields = {
            "redis_url": {"env": "REDIS_URL"},
            "rq_default_queue": {"env": "RQ_DEFAULT_QUEUE"},
            "rq_high_queue": {"env": "RQ_HIGH_QUEUE"},
            "rq_low_queue": {"env": "RQ_LOW_QUEUE"},
            "rq_dlq": {"env": "RQ_DLQ"},
            "worker_concurrency": {"env": "WORKER_CONCURRENCY"},
            "redis_max_retries": {"env": "REDIS_MAX_RETRIES"},
            "parse_timeout_ms": {"env": "PARSE_TIMEOUT_MS"},
            "metrics_auth": {"env": "METRICS_AUTH"},
            "emergency_stop_key": {"env": "EMERGENCY_STOP_KEY"},
        }


@lru_cache
def get_settings() -> WorkerConfig:
    """Return cached worker settings."""

    return WorkerConfig()


settings = get_settings()
