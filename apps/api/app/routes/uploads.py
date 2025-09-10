import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator
from ..aws import generate_presigned_url
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

@router.post("/v1/uploads/presign", response_model=PresignResponse)
def presign_upload(req: PresignRequest):
    # Sanitize filename and create deterministic key
    clean_filename = "".join(c for c in req.filename if c.isalnum() or c in '.-_')
    key = f"raw/{uuid.uuid4()}-{clean_filename}"
    
    try:
        url = generate_presigned_url(key, req.content_type, settings.presign_ttl)
        return {"key": key, "url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate presigned URL: {str(e)}")
