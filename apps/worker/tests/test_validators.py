"""Unit tests for numeric validators and OCR heuristics."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))

from apps.worker.financial.validators import validate_numeric_table
from apps.worker.ocr.select import auto_select_provider, budget_allows_ocr


def test_validate_numeric_table_detects_total_mismatch() -> None:
    table = [
        ["Metric", "2023", "2022"],
        ["Services", "100", "120"],
        ["Products", "40", "80"],
        ["Total Revenue", "150", "210"],
    ]

    result = validate_numeric_table(table)
    assert any(issue.code == "total.mismatch" for issue in result.issues)
    assert result.low_confidence


def test_validate_numeric_table_reasonableness() -> None:
    table = [
        ["Metric", "2023", "2022"],
        ["Revenue", "1,000", "900"],
        ["COGS", "(400)", "(300)"],
        ["Gross Profit", "450", "600"],
    ]

    result = validate_numeric_table(table)
    assert any(issue.code == "reasonableness.gross_profit" for issue in result.issues)
    assert result.low_confidence


def test_validate_numeric_table_parses_percentages_and_parentheses() -> None:
    table = [
        ["Metric", "Margin"],
        ["Revenue", "1,000"],
        ["Operating Margin", "15%"],
        ["Variance", "(2.5%)"],
    ]

    result = validate_numeric_table(table)
    assert result.numeric_cells >= 3
    assert result.confidence < 1.0


def test_budget_cap_enforced() -> None:
    allowed, spend = budget_allows_ocr(page_count=120, max_spend_cents=2400, cost_per_page_cents=25)
    assert not allowed
    assert spend == 3000


def test_auto_provider_selection_heuristics() -> None:
    provider = auto_select_provider({
        "raster_ratio": 0.75,
        "page_count": 2,
    })
    assert provider == "textract"

    provider = auto_select_provider({
        "table_merge_count": 3,
        "raster_ratio": 0.2,
    })
    assert provider == "azure"

    provider = auto_select_provider({
        "cost_sensitive": True,
        "page_count": 50,
    })
    assert provider == "tesseract"
