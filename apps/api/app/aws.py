from typing import Optional
import boto3
from botocore.config import Config
from .settings import settings

class S3ClientFactory:
    @staticmethod
    def create_client():
        config = Config(
            retries={'max_attempts': 3, 'mode': 'adaptive'},
            max_pool_connections=50
        )
        
        if settings.use_aws:
            return boto3.client('s3', config=config, region_name=settings.aws_region)
        else:
            return boto3.client(
                's3',
                endpoint_url=settings.s3_endpoint,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region,
                config=config
            )

def generate_presigned_url(key: str, content_type: str, file_size: int, expires_in: int = 900) -> str:
    client = S3ClientFactory.create_client()
    return client.generate_presigned_url(
        ClientMethod='put_object',
        Params={
            'Bucket': settings.s3_bucket,
            'Key': key,
            'ContentType': content_type,
            'ContentLength': file_size
        },
        ExpiresIn=expires_in
    )

def download_file(key: str) -> bytes:
    client = S3ClientFactory.create_client()
    response = client.get_object(Bucket=settings.s3_bucket, Key=key)
    return response['Body'].read()

def upload_file(key: str, data: bytes, content_type: str) -> None:
    client = S3ClientFactory.create_client()
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type
    )