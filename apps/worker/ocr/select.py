"""Provider selection heuristics and OCR budget enforcement."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from apps.worker.config import WorkerConfig


@dataclass(frozen=True)
class DocumentTraits:
    """Metadata describing the structure of a document for OCR selection."""

    page_count: int
    raster_ratio: float
    table_density: float
    has_structured_layout: bool
    detected_tables: int
    text_blocks: int


@dataclass(frozen=True)
class ProviderDecision:
    """Decision describing the selected provider and review requirement."""

    provider: str
    reason: str
    requires_review: bool = False


def estimate_job_cost_cents(page_count: int, cost_per_page: int) -> int:
    """Return the estimated OCR spend for a job in cents."""

    return max(0, page_count) * max(0, cost_per_page)


def should_fallback_to_low_cost(
    *,
    page_count: int,
    cost_per_page: int,
    max_spend: Optional[int],
) -> bool:
    """Return True if OCR should fallback to a low-cost provider."""

    if max_spend is None:
        return False
    if max_spend <= 0:
        return True
    return estimate_job_cost_cents(page_count, cost_per_page) > max_spend


def select_provider(
    traits: DocumentTraits,
    *,
    config: WorkerConfig,
) -> ProviderDecision:
    """Pick an OCR provider using a deterministic decision tree."""

    provider = "azure"
    reason = "default"
    requires_review = False

    cost_per_page = int(getattr(config, "ocr_cost_per_page", 0) or 0)
    max_spend = getattr(config, "max_job_ocr_spend", None)

    if should_fallback_to_low_cost(
        page_count=traits.page_count,
        cost_per_page=cost_per_page,
        max_spend=max_spend,
    ):
        return ProviderDecision(
            provider="tesseract",
            reason="budget_cap_exceeded",
            requires_review=True,
        )

    if traits.raster_ratio >= 0.6 or traits.detected_tables == 0:
        provider = "textract"
        reason = "image_heavy"
    elif traits.has_structured_layout or traits.table_density >= 0.4:
        provider = "azure"
        reason = "structured_layout"
    elif traits.page_count >= 30 or traits.text_blocks == 0:
        provider = "tesseract"
        reason = "cost_sensitive"
    else:
        provider = "tesseract"
        reason = "low_complexity"

    return ProviderDecision(provider=provider, reason=reason, requires_review=requires_review)


__all__ = [
    "DocumentTraits",
    "ProviderDecision",
    "estimate_job_cost_cents",
    "select_provider",
    "should_fallback_to_low_cost",
]
