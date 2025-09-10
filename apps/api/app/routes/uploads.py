import uuid
from fastapi import APIRouter
from pydantic import BaseModel, Field
from ..aws import get_s3_client, get_s3_upload_params
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
    s3 = get_s3_client()
    
    # Get upload parameters with optional KMS encryption
    upload_params = get_s3_upload_params(settings.s3_bucket, key, req.content_type)
    
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params=upload_params,
        ExpiresIn=settings.presign_ttl_seconds,
    )
    return {"key": key, "url": url}
