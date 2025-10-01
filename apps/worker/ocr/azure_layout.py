"""Azure Document Intelligence Layout OCR provider."""
from __future__ import annotations

import logging
import time
from typing import Dict, List

import requests

from . import OCRCell, OCRRateLimitError, OCRTimeoutError, _parse_numeric_hint

logger = logging.getLogger(__name__)


class AzureLayoutOCRProvider:
    """OCR provider backed by Azure Document Intelligence Layout model."""

    name = "azure"

    def __init__(self, *, endpoint: str, api_key: str, session: requests.Session | None = None) -> None:
        if not endpoint:
            raise ValueError("endpoint is required")
        if not api_key:
            raise ValueError("api_key is required")
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._session = session or requests.Session()

    def extract_cells(
        self,
        document_path: str,
        *,
        max_pages: int | None,
        timeout_ms: int | None,
    ) -> List[OCRCell]:
        timeout_seconds = (timeout_ms or 60000) / 1000
        with open(document_path, "rb") as document_file:
            payload = document_file.read()
        logger.debug("Submitting document to Azure layout OCR: %s", document_path)
        response = self._session.post(
            f"{self._endpoint}/formrecognizer/documentModels/prebuilt-layout:analyze",
            params={"api-version": "2023-07-31"},
            headers={
                "Ocp-Apim-Subscription-Key": self._api_key,
                "Content-Type": "application/pdf",
            },
            data=payload,
            timeout=timeout_seconds,
        )
        if response.status_code == 429:
            retry_after = _safe_retry_after(response.headers)
            raise OCRRateLimitError("Azure Document Intelligence throttled", retry_after=retry_after)
        if response.status_code >= 500:
            raise RuntimeError(f"Azure Document Intelligence unavailable ({response.status_code})")
        if response.status_code not in (200, 202):
            raise RuntimeError(f"Azure layout request failed: {response.status_code} {response.text}")

        if response.status_code == 202:
            operation_url = response.headers.get("operation-location")
            if not operation_url:
                raise RuntimeError("Azure layout response missing operation-location header")
            result = self._poll_operation(operation_url, timeout_seconds)
        else:
            result = response.json()

        try:
            tables = result["analyzeResult"]["tables"]
        except KeyError as exc:  # pragma: no cover - defensive
            raise RuntimeError("Azure layout response missing tables") from exc

        cells: List[OCRCell] = []
        for table in tables:
            page_number = _table_page_number(table)
            for cell in table.get("cells", []):
                text = cell.get("content", "")
                is_numeric, numeric_value = _parse_numeric_hint(text)
                cells.append(
                    OCRCell(
                        page=page_number,
                        row=int(cell.get("rowIndex", 0)),
                        column=int(cell.get("columnIndex", 0)),
                        text=text,
                        is_numeric=is_numeric,
                        numeric_value=numeric_value,
                    )
                )
        return cells

    def _poll_operation(self, url: str, timeout_seconds: float) -> Dict:
        deadline = time.time() + timeout_seconds
        backoff = 1.0
        while True:
            if time.time() > deadline:
                raise OCRTimeoutError("Azure Document Intelligence operation timed out")
            response = self._session.get(
                url,
                headers={"Ocp-Apim-Subscription-Key": self._api_key},
                timeout=min(backoff, timeout_seconds),
            )
            if response.status_code == 429:
                retry_after = _safe_retry_after(response.headers)
                raise OCRRateLimitError("Azure Document Intelligence throttled", retry_after=retry_after)
            response.raise_for_status()
            data = response.json()
            status = data.get("status")
            if status == "succeeded":
                return data
            if status == "failed":
                raise RuntimeError("Azure Document Intelligence analysis failed")
            time.sleep(backoff)
            backoff = min(backoff * 2, 15.0)


def _table_page_number(table: Dict) -> int:
    regions = table.get("boundingRegions") or []
    if regions:
        return int(regions[0].get("pageNumber", 1))
    return int(table.get("pageNumber", 1))


def _safe_retry_after(headers: Dict[str, str]) -> float | None:
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if not retry_after:
        return None
    try:
        return float(retry_after)
    except ValueError:
        return None
