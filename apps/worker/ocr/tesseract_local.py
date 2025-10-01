"""Local Tesseract OCR provider."""
from __future__ import annotations

import logging
from typing import List

try:  # pragma: no cover - optional dependency
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pytesseract = None  # type: ignore
    Image = None  # type: ignore

import fitz  # type: ignore

from . import OCRCell, OCRConfigurationError, _parse_numeric_hint

logger = logging.getLogger(__name__)


class TesseractLocalOCRProvider:
    """OCR provider using the system Tesseract binary via pytesseract."""

    name = "tesseract"

    def __init__(self, *, lang: str = "eng") -> None:
        self._lang = lang
        if pytesseract is None:
            logger.warning("pytesseract not available; Tesseract provider will raise on use")

    def extract_cells(
        self,
        document_path: str,
        *,
        max_pages: int | None,
        timeout_ms: int | None,
    ) -> List[OCRCell]:
        if pytesseract is None or Image is None:
            raise OCRConfigurationError("pytesseract and Pillow are required for Tesseract OCR")
        page_limit = max_pages or 9999
        texts: List[List[str]] = []
        with fitz.open(document_path) as document:  # type: ignore[attr-defined]
            for index, page in enumerate(document, start=1):
                if index > page_limit:
                    break
                pix = page.get_pixmap(dpi=200)
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                raw_text = pytesseract.image_to_string(image, lang=self._lang)
                rows = [row for row in raw_text.splitlines() if row.strip()]
                texts.append(rows)
        cells: List[OCRCell] = []
        for page_index, rows in enumerate(texts, start=1):
            for row_index, row_text in enumerate(rows):
                columns = [col.strip() for col in row_text.split("\t") if col.strip()]
                if not columns:
                    columns = [row_text]
                for column_index, column_text in enumerate(columns):
                    is_numeric, numeric_value = _parse_numeric_hint(column_text)
                    cells.append(
                        OCRCell(
                            page=page_index,
                            row=row_index,
                            column=column_index,
                            text=column_text,
                            is_numeric=is_numeric,
                            numeric_value=numeric_value,
                        )
                    )
        return cells
