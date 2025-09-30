"""Central configuration for API service queue features."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class APIConfig(BaseSettings):
    """Settings exposed for queue and observability features."""

    features_t1_queue: bool = True
    features_t1_financial_detector: bool = True
    features_t1_sse: bool = True
    sse_edge_budget_ms: int = 35_000
    redis_url: str = "redis://localhost:6379/0"
    rq_default_queue: str = "default"
    rq_high_queue: str = "high"
    rq_low_queue: str = "low"
    rq_dlq: str = "dead"
    worker_concurrency: int = 2
    redis_max_retries: int = 3
    parse_timeout_ms: int = 300_000
    metrics_auth: Optional[str] = None
    job_progress_ttl_seconds: int = 3600
    emergency_stop_key: str = "EMERGENCY_STOP"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        fields = {
            "features_t1_queue": {"env": "FEATURES_T1_QUEUE"},
            "features_t1_financial_detector": {"env": "FEATURES_T1_FINANCIAL_DETECTOR"},
            "features_t1_sse": {"env": "FEATURES_T1_SSE"},
            "sse_edge_budget_ms": {"env": "SSE_EDGE_BUDGET_MS"},
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
def get_settings() -> APIConfig:
    """Return cached API configuration."""

    return APIConfig()


settings = get_settings()
