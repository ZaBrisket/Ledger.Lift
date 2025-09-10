from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/ledgerlift"
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "ledger-lift"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    aws_region: str = "us-east-1"
    cors_origins: str = "http://localhost:3000"
    use_aws: bool = False
    sqs_queue_name: str = "ledger-lift-dev"
    preview_dpi: int = 144
    presign_ttl_seconds: int = 900
    s3_kms_key_id: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
CORS_ALLOWED_ORIGINS: List[str] = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
