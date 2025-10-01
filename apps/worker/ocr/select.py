"""Provider selection heuristics and OCR budget enforcement."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - only for typing
    from apps.worker.config import WorkerConfig

logger = logging.getLogger(__name__)

ALLOWED_PROVIDERS = {"azure", "textract", "tesseract"}
FALLBACK_CHAIN = ("azure", "textract", "tesseract")


@dataclass(frozen=True)
class DocumentTraits:
    """Normalized traits derived from OCR metadata."""

    page_count: int = 0
    raster_ratio: float = 0.0
    table_merges: int = 0
    has_form_like_layout: bool = False
    cost_sensitive: bool = False
    offline: bool = False


@dataclass(frozen=True)
class ProviderDecision:
    """Decision record capturing the provider and justification."""

    provider: str
    reason: str
    traits: DocumentTraits
    metadata: Mapping[str, Any]


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Safely coerce a value into a float with best-effort parsing."""

    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return default
        percent = cleaned.endswith("%")
        if percent:
            cleaned = cleaned[:-1]
        try:
            number = float(cleaned)
        except ValueError:
            return default
        return number / 100 if percent else number
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    """Safely coerce a value into an integer."""

    if value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if not match:
            return default
        try:
            return int(match.group())
        except ValueError:
            return default
    return default


def _traits_from_metadata(metadata: Mapping[str, Any]) -> DocumentTraits:
    """Derive document traits from arbitrary metadata."""

    raster_ratio = _safe_float(
        metadata.get("raster_ratio") or metadata.get("raster_to_text_ratio")
    )
    table_merges = _safe_int(
        metadata.get("table_merge_count") or metadata.get("table_merge_ops")
    )
    page_count = _safe_int(metadata.get("page_count") or metadata.get("pages"))
    cost_sensitive = bool(metadata.get("cost_sensitive")) or bool(metadata.get("budget_fallback"))
    offline = bool(metadata.get("offline"))
    has_form_like_layout = bool(metadata.get("has_form_like_layout"))
    return DocumentTraits(
        page_count=page_count,
        raster_ratio=raster_ratio,
        table_merges=table_merges,
        has_form_like_layout=has_form_like_layout,
        cost_sensitive=cost_sensitive,
        offline=offline,
    )


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


def select_provider(
    traits: DocumentTraits,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> ProviderDecision:
    """Return a provider decision from explicit traits and metadata."""

    metadata = metadata or {}
    preferred = str(metadata.get("preferred_provider") or "").lower()
    if preferred in ALLOWED_PROVIDERS:
        return ProviderDecision(
            provider=preferred,
            reason="preferred-provider",
            traits=traits,
            metadata=metadata,
        )

    if traits.cost_sensitive or traits.offline:
        return ProviderDecision(
            provider="tesseract",
            reason="cost-sensitive",
            traits=traits,
            metadata=metadata,
        )

    if traits.page_count >= 40 and traits.raster_ratio < 0.45:
        return ProviderDecision(
            provider="tesseract",
            reason="long-document-low-raster",
            traits=traits,
            metadata=metadata,
        )

    if traits.raster_ratio >= 0.6:
        return ProviderDecision(
            provider="textract",
            reason="high-raster-ratio",
            traits=traits,
            metadata=metadata,
        )

    if traits.table_merges >= 2 or traits.has_form_like_layout:
        return ProviderDecision(
            provider="azure",
            reason="structured-form",
            traits=traits,
            metadata=metadata,
        )

    if traits.raster_ratio >= 0.4:
        return ProviderDecision(
            provider="textract",
            reason="moderate-raster",
            traits=traits,
            metadata=metadata,
        )

    return ProviderDecision(
        provider="azure",
        reason="default-structured",
        traits=traits,
        metadata=metadata,
    )


def auto_select_provider(metadata: Mapping[str, Any] | None = None) -> str:
    """Select an OCR provider based on document metadata heuristics."""

    metadata = metadata or {}
    traits = _traits_from_metadata(metadata)
    decision = select_provider(traits, metadata=metadata)
    logger.info(
        "ocr_provider_auto_selected",
        extra={
            "provider": decision.provider,
            "reason": decision.reason,
            "page_count": decision.traits.page_count,
            "raster_ratio": decision.traits.raster_ratio,
            "table_merges": decision.traits.table_merges,
        },
    )
    return decision.provider


def resolve_provider_name(
    config: "WorkerConfig",
    *,
    metadata: Mapping[str, Any] | None = None,
) -> tuple[str, ProviderDecision | None]:
    """Resolve the provider name according to configuration and metadata."""

    metadata = metadata or {}
    mode = (config.ocr_provider_mode or "explicit").strip().lower()
    explicit = (config.ocr_provider or "").strip().lower()
    if mode not in {"explicit", "auto"}:
        raise ValueError(f"Unsupported OCR provider mode: {mode}")

    if mode == "explicit":
        if explicit not in ALLOWED_PROVIDERS:
            raise ValueError("OCR_PROVIDER must be set when mode=explicit")
        return explicit, None

    traits = _traits_from_metadata(metadata)
    decision = select_provider(traits, metadata=metadata)

    ordered_candidates = [decision.provider]
    for fallback in FALLBACK_CHAIN:
        if fallback not in ordered_candidates:
            ordered_candidates.append(fallback)

    for candidate in ordered_candidates:
        resolved = _prefer_available_provider(candidate, config=config)
        if resolved in ALLOWED_PROVIDERS:
            return resolved, decision

    return "tesseract", decision


__all__ = [
    "ALLOWED_PROVIDERS",
    "DocumentTraits",
    "ProviderDecision",
    "auto_select_provider",
    "budget_allows_ocr",
    "estimate_job_spend",
    "resolve_provider_name",
    "select_provider",
]
