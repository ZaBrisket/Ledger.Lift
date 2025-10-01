"""AWS Textract OCR provider for table extraction."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, TYPE_CHECKING

try:
    import boto3
    from boto3.session import Session as Boto3Session
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    boto3 = None  # type: ignore[assignment]
    Config = None  # type: ignore[assignment]
    BotoCoreError = Exception  # type: ignore[assignment]
    ClientError = Exception  # type: ignore[assignment]
    Boto3Session = Any  # type: ignore[assignment]

if TYPE_CHECKING and not BOTO3_AVAILABLE:  # pragma: no cover - typing aid
    from boto3.session import Session as Boto3Session  # type: ignore

from . import OCRCell, OCRConfigurationError, OCRRateLimitError, _parse_numeric_hint

logger = logging.getLogger(__name__)


class AWSTextractOCRProvider:
    """OCR provider backed by AWS Textract AnalyzeDocument API."""

    name = "textract"

    def __init__(
        self,
        *,
        region: str,
        access_key: str | None = None,
        secret_key: str | None = None,
        session: Boto3Session | None = None,
    ) -> None:
        if not BOTO3_AVAILABLE:
            raise OCRConfigurationError("boto3 is required for the Textract provider")
        if not region:
            raise OCRConfigurationError("AWS_TEXTRACT_REGION is required")
        self._region = region
        self._session = session or boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        self._base_config = Config(retries={"max_attempts": 2})

    def extract_cells(
        self,
        document_path: str,
        *,
        max_pages: int | None,
        timeout_ms: int | None,
    ) -> List[OCRCell]:
        timeout_seconds = (timeout_ms or 60000) / 1000
        client_config = self._base_config.merge(
            Config(read_timeout=timeout_seconds, connect_timeout=timeout_seconds)
        )
        client = self._session.client("textract", config=client_config)

        with open(document_path, "rb") as document_file:
            payload = document_file.read()
        try:
            response = client.analyze_document(
                Document={"Bytes": payload},
                FeatureTypes=["TABLES"],
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"ProvisionedThroughputExceededException", "ThrottlingException"}:
                raise OCRRateLimitError("Textract throttled", retry_after=_retry_after_from_error(exc))
            raise
        except BotoCoreError as exc:
            raise RuntimeError(f"Textract invocation failed: {exc}") from exc

        blocks = response.get("Blocks", [])
        block_map: Dict[str, Dict] = {block.get("Id"): block for block in blocks if block.get("Id")}
        cells: List[OCRCell] = []
        for block in blocks:
            if block.get("BlockType") != "CELL":
                continue
            text = _resolve_cell_text(block, block_map)
            is_numeric, numeric_value = _parse_numeric_hint(text)
            page = int(block.get("Page", 1))
            cells.append(
                OCRCell(
                    page=page,
                    row=int(block.get("RowIndex", 0)),
                    column=int(block.get("ColumnIndex", 0)),
                    text=text,
                    is_numeric=is_numeric,
                    numeric_value=numeric_value,
                )
            )
        return cells


def _resolve_cell_text(cell_block: Dict, block_map: Dict[str, Dict]) -> str:
    relationships = cell_block.get("Relationships", [])
    texts: List[str] = []
    for relation in relationships:
        if relation.get("Type") != "CHILD":
            continue
        for child_id in relation.get("Ids", []):
            child_block = block_map.get(child_id)
            if not child_block:
                continue
            if child_block.get("BlockType") == "WORD" and "Text" in child_block:
                texts.append(child_block["Text"])
            elif child_block.get("BlockType") == "SELECTION_ELEMENT" and child_block.get("SelectionStatus") == "SELECTED":
                texts.append("X")
    return " ".join(texts).strip()


def _retry_after_from_error(error: ClientError) -> float | None:
    metadata = error.response.get("ResponseMetadata", {})
    http_headers = metadata.get("HTTPHeaders", {})
    retry_after = http_headers.get("retry-after") or http_headers.get("Retry-After")
    if not retry_after:
        return None
    try:
        return float(retry_after)
    except ValueError:
        return None
