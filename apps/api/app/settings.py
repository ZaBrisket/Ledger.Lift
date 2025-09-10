from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # Database settings
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ledgerlift"
    db_pool_size: int = 20
    db_max_overflow: int = 30
    db_pool_timeout: int = 30
    
    # S3 settings
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "ledger-lift"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    aws_region: str = "us-east-1"
    use_aws: bool = False
    
    # S3 Circuit breaker settings
    s3_failure_threshold: int = 5
    s3_recovery_timeout: int = 60
    
    # API settings
    cors_origins: str = "http://localhost:3000"
    max_file_size: int = 100 * 1024 * 1024  # 100MB
    presign_ttl: int = 900
    
    # Timeout settings (seconds)
    default_request_timeout: int = 30
    upload_timeout: int = 120
    
    # Logging settings
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Health check settings
    health_cache_ttl: int = 30
    
    # Performance settings
    enable_request_logging: bool = True
    enable_performance_monitoring: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    def __post_init__(self):
        if self.use_aws and not all([self.aws_access_key_id, self.aws_secret_access_key]):
            raise ValueError("AWS credentials required when use_aws=True")

settings = Settings()
CORS_ALLOWED_ORIGINS: List[str] = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
