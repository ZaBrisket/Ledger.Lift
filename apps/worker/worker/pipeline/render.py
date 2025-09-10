from typing import List
import fitz  # PyMuPDF
from pathlib import Path

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
