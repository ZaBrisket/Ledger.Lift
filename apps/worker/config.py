"""Worker configuration for queue processing and observability."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class WorkerConfig(BaseSettings):
    """Settings for the worker process."""

    features_t1_queue: bool = True
    features_t1_financial_detector: bool = True
    features_t1_financial_ml: bool = False
    features_t1_cas_phash: bool = True
    features_t2_ocr: bool = False
    features_t2_review_ui: bool = True
    ocr_provider: Optional[str] = None
    ocr_provider_mode: str = "explicit"
    ocr_page_timeout_ms: int = 60000
    ocr_max_pages: int = 50
    ocr_cost_per_page_cents: int = 0
    max_job_ocr_spend_cents: int = 240
    azure_di_endpoint: Optional[str] = None
    azure_di_key: Optional[str] = None
    aws_textract_region: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    ocr_tps_textract: Optional[float] = None
    ocr_tps_azure: Optional[float] = None
    ocr_circuit_open_secs: int = 60
    cas_normalize_pdf: bool = True
    phash_pages: int = 3
    phash_distance_max: int = 6
    parser_max_schedules: int = 10
    parser_max_empty_pages: int = 20
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
    job_progress_ttl_seconds: int = 3600

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        fields = {
            "features_t1_queue": {"env": "FEATURES_T1_QUEUE"},
            "features_t1_financial_detector": {"env": "FEATURES_T1_FINANCIAL_DETECTOR"},
            "features_t1_financial_ml": {"env": "FEATURES_T1_FINANCIAL_ML"},
            "features_t1_cas_phash": {"env": "FEATURES_T1_CAS_PHASH"},
            "features_t2_ocr": {"env": "FEATURES_T2_OCR"},
            "features_t2_review_ui": {"env": "FEATURES_T2_REVIEW_UI"},
            "ocr_provider": {"env": "OCR_PROVIDER"},
            "ocr_provider_mode": {"env": "OCR_PROVIDER_MODE"},
            "ocr_page_timeout_ms": {"env": "OCR_PAGE_TIMEOUT_MS"},
            "ocr_max_pages": {"env": "OCR_MAX_PAGES"},
            "ocr_cost_per_page_cents": {"env": "OCR_COST_PER_PAGE"},
            "max_job_ocr_spend_cents": {"env": "MAX_JOB_OCR_SPEND"},
            "azure_di_endpoint": {"env": "AZURE_DI_ENDPOINT"},
            "azure_di_key": {"env": "AZURE_DI_KEY"},
            "aws_textract_region": {"env": "AWS_TEXTRACT_REGION"},
            "aws_access_key_id": {"env": "AWS_ACCESS_KEY_ID"},
            "aws_secret_access_key": {"env": "AWS_SECRET_ACCESS_KEY"},
            "ocr_tps_textract": {"env": "OCR_TPS_TEXTRACT"},
            "ocr_tps_azure": {"env": "OCR_TPS_AZURE"},
            "ocr_circuit_open_secs": {"env": "OCR_CIRCUIT_OPEN_SECS"},
            "cas_normalize_pdf": {"env": "CAS_NORMALIZE_PDF"},
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
            "job_progress_ttl_seconds": {"env": "JOB_PROGRESS_TTL_SECONDS"},
            "phash_pages": {"env": "PHASH_PAGES"},
            "phash_distance_max": {"env": "PHASH_DISTANCE_MAX"},
            "parser_max_schedules": {"env": "PARSER_MAX_SCHEDULES"},
            "parser_max_empty_pages": {"env": "PARSER_MAX_EMPTY_PAGES"},
        }


@lru_cache
def get_settings() -> WorkerConfig:
    """Return cached worker settings."""

    return WorkerConfig()


settings = get_settings()
