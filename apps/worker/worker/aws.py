import boto3
from .settings import settings

def get_s3_client():
    """Get S3 client configured for either AWS or MinIO based on settings.use_aws"""
    if settings.use_aws:
        # Use real AWS S3
        return boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
    else:
        # Use MinIO/LocalStack
        return boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )

def get_sqs_client():
    """Get SQS client configured for either AWS or LocalStack based on settings.use_aws"""
    if settings.use_aws:
        # Use real AWS SQS
        return boto3.client(
            "sqs",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
    else:
        # Use LocalStack
        return boto3.client(
            "sqs",
            endpoint_url=settings.s3_endpoint.replace("9000", "4566"),  # LocalStack SQS port
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )