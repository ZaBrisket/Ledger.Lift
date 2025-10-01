"""Tests for OCR provider selection heuristics."""
from __future__ import annotations

from types import SimpleNamespace
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[3]))

from apps.worker.ocr.select import (  # noqa: E402
    DocumentTraits,
    ProviderDecision,
    estimate_job_cost_cents,
    select_provider,
    should_fallback_to_low_cost,
)


def make_config(**overrides):
    return SimpleNamespace(
        ocr_cost_per_page=overrides.get("ocr_cost_per_page", 12),
        max_job_ocr_spend=overrides.get("max_job_ocr_spend", 240),
    )


def test_estimate_job_cost_cents() -> None:
    assert estimate_job_cost_cents(10, 15) == 150
    assert estimate_job_cost_cents(-5, 10) == 0


@pytest.mark.parametrize(
    "traits,expected",
    [
        (
            DocumentTraits(
                page_count=5,
                raster_ratio=0.8,
                table_density=0.1,
                has_structured_layout=False,
                detected_tables=0,
                text_blocks=2,
            ),
            "textract",
        ),
        (
            DocumentTraits(
                page_count=4,
                raster_ratio=0.2,
                table_density=0.5,
                has_structured_layout=True,
                detected_tables=3,
                text_blocks=10,
            ),
            "azure",
        ),
        (
            DocumentTraits(
                page_count=60,
                raster_ratio=0.2,
                table_density=0.2,
                has_structured_layout=False,
                detected_tables=2,
                text_blocks=0,
            ),
            "tesseract",
        ),
    ],
)
def test_select_provider_heuristics(traits: DocumentTraits, expected: str) -> None:
    decision = select_provider(traits, config=make_config())

    assert isinstance(decision, ProviderDecision)
    assert decision.provider == expected


def test_budget_cap_triggers_review() -> None:
    traits = DocumentTraits(
        page_count=20,
        raster_ratio=0.3,
        table_density=0.5,
        has_structured_layout=True,
        detected_tables=5,
        text_blocks=5,
    )

    decision = select_provider(traits, config=make_config(max_job_ocr_spend=100))

    assert decision.provider == "tesseract"
    assert decision.requires_review
    assert decision.reason == "budget_cap_exceeded"


def test_should_fallback_to_low_cost_handles_unset_budget() -> None:
    assert not should_fallback_to_low_cost(page_count=10, cost_per_page=12, max_spend=None)
    assert should_fallback_to_low_cost(page_count=10, cost_per_page=12, max_spend=100)
