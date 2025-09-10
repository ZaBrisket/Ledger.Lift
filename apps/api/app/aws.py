import boto3
from botocore.client import BaseClient
from typing import Dict, Any
from .settings import settings


def get_s3_client() -> BaseClient:
    """Get S3 client configured for AWS or MinIO based on USE_AWS flag."""
    if settings.use_aws:
        # Production AWS - no endpoint_url
        client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
    else:
        # Local MinIO - with endpoint_url
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
    return client


def get_sqs_client() -> BaseClient:
    """Get SQS client configured for AWS or LocalStack based on USE_AWS flag."""
    if settings.use_aws:
        # Production AWS - no endpoint_url
        client = boto3.client(
            "sqs",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
    else:
        # Local LocalStack - with endpoint_url (port 4566)
        client = boto3.client(
            "sqs",
            endpoint_url="http://localhost:4566",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
    return client


def get_s3_put_params(bucket: str, key: str, content_type: str = None) -> Dict[str, Any]:
    """Get S3 put_object parameters with optional KMS encryption."""
    params = {
        "Bucket": bucket,
        "Key": key
    }
    
    if content_type:
        params["ContentType"] = content_type
    
    # Add KMS encryption if configured
    if settings.s3_kms_key_id and settings.use_aws:
        params["ServerSideEncryption"] = "aws:kms"
        params["SSEKMSKeyId"] = settings.s3_kms_key_id
    
    return params


def generate_presigned_url(client: BaseClient, method: str, params: Dict[str, Any], expires_in: int = None) -> str:
    """Generate presigned URL with configurable TTL."""
    ttl = expires_in or settings.presign_ttl_seconds
    return client.generate_presigned_url(
        ClientMethod=method,
        Params=params,
        ExpiresIn=ttl
    )