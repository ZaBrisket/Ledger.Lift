import uuid
from fastapi import APIRouter
from pydantic import BaseModel, Field
from ..settings import settings
from ..aws import get_s3_client, get_s3_put_params, generate_presigned_url
from ..telemetry import get_tracer, adapter_s3_counter

router = APIRouter()

class PresignRequest(BaseModel):
    filename: str
    content_type: str = Field(alias="content_type")

class PresignResponse(BaseModel):
    key: str
    url: str

@router.post("/v1/uploads/presign", response_model=PresignResponse)
def presign_upload(req: PresignRequest):
    tracer = get_tracer()
    
    with tracer.start_as_current_span("presign_upload") as span:
        span.set_attribute("filename", req.filename)
        span.set_attribute("use_aws", settings.use_aws)
        
        key = f"raw/{uuid.uuid4()}-{req.filename}"
        s3 = get_s3_client()
        
        # Get put parameters with optional KMS encryption
        params = get_s3_put_params(settings.s3_bucket, key, req.content_type)
        
        # Generate presigned URL with configurable TTL
        url = generate_presigned_url(s3, "put_object", params)
        
        # Record metric
        adapter_s3_counter.add(1, {"use_aws": str(settings.use_aws)})
        
        span.set_attribute("s3_key", key)
        
        return {"key": key, "url": url}
