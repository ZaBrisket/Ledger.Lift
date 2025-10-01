"""Provider selection heuristics and OCR budget enforcement."""
from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - only for typing
    from apps.worker.config import WorkerConfig

ALLOWED_PROVIDERS = {"azure", "textract", "tesseract"}


def estimate_job_spend(page_count: int, cost_per_page_cents: int) -> int:
    """Return the estimated OCR spend in cents for a job."""
    if page_count < 0:
        raise ValueError("page_count must be non-negative")
    if cost_per_page_cents < 0:
        raise ValueError("cost_per_page_cents must be non-negative")
    return page_count * cost_per_page_cents


def budget_allows_ocr(
    page_count: Optional[int],
    max_spend_cents: Optional[int],
    cost_per_page_cents: Optional[int],
) -> Tuple[bool, int]:
    """Determine whether OCR is within budget.

    Returns a tuple ``(allowed, estimated_cost)``.
    """
    if page_count is None or page_count <= 0:
        return True, 0
    per_page = cost_per_page_cents or 0
    max_spend = max_spend_cents or 0
    estimated = estimate_job_spend(page_count, per_page)
    if max_spend == 0:
        return True, estimated
    return estimated <= max_spend, estimated


def _prefer_available_provider(
    candidate: str,
    *,
    config: "WorkerConfig",
) -> str:
    if candidate == "azure" and not (config.azure_di_endpoint and config.azure_di_key):
        return "tesseract"
    if candidate == "textract" and not config.aws_textract_region:
        return "tesseract"
    return candidate


def auto_select_provider(metadata: Mapping[str, Any] | None = None) -> str:
    """Select an OCR provider based on document metadata heuristics."""
    metadata = metadata or {}
    preferred = str(metadata.get("preferred_provider") or "").lower()
    if preferred in ALLOWED_PROVIDERS:
        return preferred

    cost_sensitive = bool(metadata.get("cost_sensitive")) or bool(metadata.get("offline"))
    raster_ratio = float(metadata.get("raster_ratio") or metadata.get("raster_to_text_ratio") or 0.0)
    table_merges = int(metadata.get("table_merge_count") or metadata.get("table_merge_ops") or 0)
    page_count = int(metadata.get("page_count") or metadata.get("pages") or 0)

    if cost_sensitive or metadata.get("budget_fallback"):
        return "tesseract"

    if page_count >= 40 and raster_ratio < 0.45:
        return "tesseract"

    if raster_ratio >= 0.6:
        return "textract"

    if table_merges >= 2 or metadata.get("has_form_like_layout"):
        return "azure"

    if raster_ratio >= 0.4:
        return "textract"

    return "azure"


def resolve_provider_name(
    config: "WorkerConfig",
    *,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    """Resolve the provider name according to configuration and metadata."""
    mode = (config.ocr_provider_mode or "explicit").strip().lower()
    explicit = (config.ocr_provider or "").strip().lower()
    if mode not in {"explicit", "auto"}:
        raise ValueError(f"Unsupported OCR provider mode: {mode}")

    if mode == "explicit":
        if explicit not in ALLOWED_PROVIDERS:
            raise ValueError("OCR_PROVIDER must be set when mode=explicit")
        return explicit

    candidate = auto_select_provider(metadata)
    candidate = _prefer_available_provider(candidate, config=config)
    if candidate not in ALLOWED_PROVIDERS:
        return "tesseract"
    return candidate


__all__ = [
    "ALLOWED_PROVIDERS",
    "auto_select_provider",
    "budget_allows_ocr",
    "estimate_job_spend",
    "resolve_provider_name",
]
