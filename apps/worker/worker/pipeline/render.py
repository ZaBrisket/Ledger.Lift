from typing import List
import fitz  # PyMuPDF
from pathlib import Path
import io
from ..aws import get_s3_client
from ..settings import settings

def render_pdf_preview(pdf_path: str) -> List[Path]:
    doc = fitz.open(pdf_path)
    out_paths = []
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(dpi=72)
        out = Path(f"/tmp/preview_{i}.png")
        pix.save(out.as_posix())
        out_paths.append(out)
    doc.close()
    return out_paths

def render_pdf_preview_to_s3(doc_id: str, pdf_path: str, dpi: int = 144) -> List[str]:
    """Render PDF pages to PNG and upload to S3 previews/ folder"""
    doc = fitz.open(pdf_path)
    s3 = get_s3_client()
    uploaded_keys = []
    
    for i, page in enumerate(doc, start=1):
        # Render page at specified DPI
        pix = page.get_pixmap(dpi=dpi)
        
        # Convert to bytes
        img_data = pix.tobytes("png")
        
        # Upload to S3
        key = f"previews/{doc_id}/page-{i}.png"
        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=img_data,
            ContentType="image/png"
        )
        uploaded_keys.append(key)
    
    doc.close()
    return uploaded_keys
