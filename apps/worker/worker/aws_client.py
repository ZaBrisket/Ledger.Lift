import os
import boto3
from botocore.config import Config

class WorkerS3Client:
    def __init__(self):
        self.use_aws = os.getenv('USE_AWS', 'false').lower() == 'true'
        self.s3_endpoint = os.getenv('S3_ENDPOINT', 'http://localhost:9000')
        self.s3_bucket = os.getenv('S3_BUCKET', 'ledger-lift')
        self.aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID', 'minioadmin')
        self.aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY', 'minioadmin')
        self.aws_region = os.getenv('AWS_REGION', 'us-east-1')
        
        config = Config(
            retries={'max_attempts': 3, 'mode': 'adaptive'},
            max_pool_connections=50
        )
        
        if self.use_aws:
            self.client = boto3.client('s3', config=config, region_name=self.aws_region)
        else:
            self.client = boto3.client(
                's3',
                endpoint_url=self.s3_endpoint,
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.aws_region,
                config=config
            )

    def download_file(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.s3_bucket, Key=key)
        return response['Body'].read()

    def upload_file(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.s3_bucket,
            Key=key,
            Body=data,
            ContentType=content_type
        )