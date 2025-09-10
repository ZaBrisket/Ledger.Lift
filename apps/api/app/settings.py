from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ledgerlift"
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "ledger-lift"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    aws_region: str = "us-east-1"
    cors_origins: str = "http://localhost:3000"
    
    # New production settings
    use_aws: bool = False
    max_file_size: int = 100 * 1024 * 1024  # 100MB
    presign_ttl: int = 900

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    def __post_init__(self):
        if self.use_aws and not all([self.aws_access_key_id, self.aws_secret_access_key]):
            raise ValueError("AWS credentials required when use_aws=True")

settings = Settings()
CORS_ALLOWED_ORIGINS: List[str] = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
