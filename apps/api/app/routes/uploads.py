import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator
from ..aws import s3_client
from ..settings import settings

router = APIRouter()

class PresignRequest(BaseModel):
    filename: str
    content_type: str = Field(alias="content_type")
    file_size: int
    
    @validator('filename')
    def validate_filename(cls, v):
        if not v or '..' in v or '/' in v:
            raise ValueError('Invalid filename')
        return v
    
    @validator('content_type')
    def validate_content_type(cls, v):
        allowed = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
        if v not in allowed:
            raise ValueError('Unsupported content type')
        return v
    
    @validator('file_size')
    def validate_file_size(cls, v):
        if v > settings.max_file_size:
            raise ValueError(f'File too large. Max: {settings.max_file_size} bytes')
        return v

class PresignResponse(BaseModel):
    key: str
    url: str

class PresignPostResponse(BaseModel):
    key: str
    url: str
    fields: dict

@router.post("/v1/uploads/presign", response_model=PresignResponse)
async def presign_upload(req: PresignRequest):
    # Sanitize filename and create deterministic key
    clean_filename = "".join(c for c in req.filename if c.isalnum() or c in '.-_')
    key = f"raw/{uuid.uuid4()}-{clean_filename}"
    
    try:
        url = await s3_client.generate_presigned_url(key, req.content_type, req.file_size, settings.presign_ttl)
        return {"key": key, "url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate presigned URL: {str(e)}")

@router.post("/v1/uploads/presign-post", response_model=PresignPostResponse)
async def presign_upload_post(req: PresignRequest):
    """Generate presigned POST data for multipart uploads (better for large files)"""
    # Sanitize filename and create deterministic key
    clean_filename = "".join(c for c in req.filename if c.isalnum() or c in '.-_')
    key = f"raw/{uuid.uuid4()}-{clean_filename}"
    
    try:
        result = await s3_client.generate_presigned_post(
            key, 
            req.content_type, 
            req.file_size, 
            settings.presign_ttl
        )
        return {
            "key": key, 
            "url": result["url"],
            "fields": result["fields"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate presigned POST: {str(e)}")
