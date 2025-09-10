from typing import List
import fitz  # PyMuPDF
from pathlib import Path
import os
import io
from ..aws import get_s3_client

def render_pdf_preview(pdf_path: str) -> List[Path]:
    """Original function for local preview generation."""
    doc = fitz.open(pdf_path)
    out_paths = []
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(dpi=72)
        out = Path(f"/tmp/preview_{i}.png")
        pix.save(out.as_posix())
        out_paths.append(out)
    doc.close()
    return out_paths

def render_pdf_preview_to_s3(doc_id: str, pdf_path: str) -> List[str]:
    """Render PDF pages as images and upload to S3 previews/ folder."""
    doc = fitz.open(pdf_path)
    s3_client = get_s3_client()
    bucket = os.getenv("S3_BUCKET", "ledger-lift")
    preview_dpi = int(os.getenv("PREVIEW_DPI", "144"))
    
    uploaded_keys = []
    
    for i, page in enumerate(doc, start=1):
        # Render page at specified DPI
        pix = page.get_pixmap(dpi=preview_dpi)
        
        # Convert to bytes
        img_bytes = pix.tobytes("png")
        
        # Generate S3 key
        s3_key = f"previews/{doc_id}/page-{i}.png"
        
        # Upload to S3
        s3_client.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=img_bytes,
            ContentType="image/png"
        )
        
        uploaded_keys.append(s3_key)
    
    doc.close()
    return uploaded_keys
