from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "ledger-lift"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    aws_region: str = "us-east-1"
    
    # AWS adapter settings
    use_aws: bool = False
    sqs_queue_name: str = "ledger-lift-dev"
    
    # OCR settings
    ocr_enabled: bool = False
    
    # Consensus settings
    consensus_enabled: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()