import uuid
import boto3
from fastapi import APIRouter
from pydantic import BaseModel, Field
from ..settings import settings

router = APIRouter()

class PresignRequest(BaseModel):
    filename: str
    content_type: str = Field(alias="content_type")

class PresignResponse(BaseModel):
    key: str
    url: str

@router.post("/v1/uploads/presign", response_model=PresignResponse)
def presign_upload(req: PresignRequest):
    key = f"raw/{uuid.uuid4()}-{req.filename}"
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": req.content_type},
        ExpiresIn=900,
    )
    return {"key": key, "url": url}
