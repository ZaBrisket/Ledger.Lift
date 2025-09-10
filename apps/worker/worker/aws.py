import boto3
from botocore.client import BaseClient
import os


def get_s3_client() -> BaseClient:
    """Get S3 client configured for AWS or MinIO based on USE_AWS flag."""
    use_aws = os.getenv("USE_AWS", "false").lower() == "true"
    
    if use_aws:
        # Production AWS - no endpoint_url
        client = boto3.client(
            "s3",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )
    else:
        # Local MinIO - with endpoint_url
        client = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT", "http://localhost:9000"),
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )
    return client


def get_sqs_client() -> BaseClient:
    """Get SQS client configured for AWS or LocalStack based on USE_AWS flag."""
    use_aws = os.getenv("USE_AWS", "false").lower() == "true"
    
    if use_aws:
        # Production AWS - no endpoint_url
        client = boto3.client(
            "sqs",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )
    else:
        # Local LocalStack - with endpoint_url (port 4566)
        client = boto3.client(
            "sqs",
            endpoint_url="http://localhost:4566",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )
    return client