"""Unit tests for financial numeric validators."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))

from apps.worker.financial.validators import (  # noqa: E402
    TableValidationResult,
    parse_numeric,
    validate_table,
)


def test_parse_numeric_handles_parentheses_and_percentages() -> None:
    assert parse_numeric("(1,234)") == -1234
    assert math.isclose(parse_numeric("7.5%") or 0.0, 0.075)
    assert parse_numeric("$3,210") == 3210
    assert parse_numeric("not a number") is None


def test_validate_table_detects_total_mismatch() -> None:
    headers = ["Line", "2023", "2022"]
    rows = [
        ["Revenue", "100", "90"],
        ["COGS", "(40)", "(30)"],
        ["Gross Profit", "60", "60"],
        ["Total", "65", "65"],
    ]

    result = validate_table(headers, rows)

    assert isinstance(result, TableValidationResult)
    assert result.issues, "Mismatch should generate at least one issue"
    assert not result.is_valid
    assert result.requires_review


def test_validate_table_passes_consistent_financials() -> None:
    headers = ["Line", "2023", "2022"]
    rows = [
        ["Revenue", "100", "110"],
        ["COGS", "(40)", "(55)"],
        ["Gross Profit", "60", "55"],
        ["Total", "60", "55"],
    ]

    result = validate_table(headers, rows)

    assert result.is_valid
    assert result.confidence > 0.65
    assert not result.requires_review
