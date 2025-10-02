from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AnyUrl

class T3Settings(BaseSettings):
    # Feature flags
    features_t3_audit: bool = Field(default=False, alias="FEATURES_T3_AUDIT")
    features_t3_gdpr: bool  = Field(default=False, alias="FEATURES_T3_GDPR")
    features_t3_costs: bool = Field(default=False, alias="FEATURES_T3_COSTS")
    enable_partial_export: bool = Field(default=False, alias="ENABLE_PARTIAL_EXPORT")

    # Audit
    audit_batch_size: int = Field(default=50, ge=1, le=1000, alias="AUDIT_BATCH_SIZE")
    audit_flush_interval_ms: int = Field(default=1000, ge=50, le=60000, alias="AUDIT_FLUSH_INTERVAL_MS")
    audit_max_queue_size: int = Field(default=10000, ge=100, le=1000000, alias="AUDIT_MAX_QUEUE_SIZE")
    audit_durable_mode: str = Field(default="memory", alias="AUDIT_DURABLE_MODE")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")

    # Tracing
    trace_enabled: bool = Field(default=True, alias="TRACE_ENABLED")
    trace_sample_rate: float = Field(default=1.0, ge=0.0, le=1.0, alias="TRACE_SAMPLE_RATE")

    # Deletion
    deletion_max_duration_seconds: int = Field(default=120, alias="DELETION_MAX_DURATION_SECONDS")
    deletion_sweep_interval_seconds: int = Field(default=300, alias="DELETION_SWEEP_INTERVAL_SECONDS")

    # Costs
    cost_per_page_cents: int = Field(default=12, ge=0, le=1000, alias="COST_PER_PAGE_CENTS")
    max_job_cost_cents: int = Field(default=24000, ge=0, alias="MAX_JOB_COST_CENTS")
    cost_reconciliation_threshold: float = Field(default=0.05, ge=0.0, le=1.0, alias="COST_RECONCILIATION_THRESHOLD")

    # DB & API
    database_url: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:5432/ledgerlift", alias="DATABASE_URL")
    api_base_url: AnyUrl | None = Field(default=None, alias="NEXT_PUBLIC_API_URL")

    model_config = SettingsConfigDict(env_file='.env', case_sensitive=False)

settings = T3Settings()
