"""Numeric validation helpers for financial schedules.

The validator operates on a lightweight structure compatible with the
``TableCandidate`` used by the detector. The module focuses on common
consistency checks that routinely appear in exported financial
statements:

* Totals across rows/columns.
* Relationship checks such as ``gross profit = revenue - cogs``.
* Parentheses negatives and percent parsing.

The helpers are intentionally defensive – cells may contain stray
characters or be missing entirely. The validator returns a structured
``TableValidationResult`` describing issues and a confidence score that
down-weights noisy or contradictory tables. Callers can route low
confidence tables to the manual review UI.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Iterable, List, Optional, Sequence


Numeric = float


TOTAL_KEYWORDS = {
    "total",
    "subtotal",
    "net income",
    "net loss",
    "balance",
}

REVENUE_KEYWORDS = {"revenue", "sales"}
COGS_KEYWORDS = {"cogs", "cost of goods", "cost of revenue"}
GROSS_PROFIT_KEYWORDS = {"gross profit"}

NEGATIVE_PAREN_RE = re.compile(r"^\((.+)\)$")
PERCENT_RE = re.compile(r"^([-+]?\d+(?:\.\d+)?)%$")


@dataclass
class ValidationIssue:
    """Represents a failed validation check."""

    message: str
    row: Optional[int] = None
    column: Optional[int] = None
    severity: str = "error"


@dataclass
class TableValidationResult:
    """Result of validating a financial table."""

    confidence: float
    issues: List[ValidationIssue]

    @property
    def is_valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def requires_review(self) -> bool:
        return (not self.is_valid) or self.confidence < 0.65


def _normalize(text: Optional[str]) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def parse_numeric(cell: Optional[str]) -> Optional[Numeric]:
    """Parse numeric strings supporting parentheses and percentages."""

    if cell is None:
        return None
    text = cell.strip()
    if not text:
        return None

    text = text.replace(",", "")
    match = NEGATIVE_PAREN_RE.match(text)
    sign = 1.0
    if match:
        text = match.group(1)
        sign = -1.0

    percent_match = PERCENT_RE.match(text)
    if percent_match:
        try:
            value = float(percent_match.group(1)) / 100.0
        except ValueError:
            return None
        return sign * value

    # Handle stray currency symbols or trailing annotations.
    cleaned = re.sub(r"[^0-9.+-]", "", text)
    if cleaned.count("-") > 1:
        return None
    if cleaned in {"", "+", "-"}:
        return None
    try:
        return sign * float(cleaned)
    except ValueError:
        return None


def _iter_numeric_rows(rows: Sequence[Sequence[Optional[str]]]) -> Iterable[List[Optional[Numeric]]]:
    for row in rows:
        yield [parse_numeric(cell) for cell in row]


def validate_table(
    headers: Sequence[str], rows: Sequence[Sequence[Optional[str]]]
) -> TableValidationResult:
    """Validate numeric consistency for a table.

    The validator performs best-effort checks using heuristics that align
    with common accounting schedules. Confidence decreases as checks fail
    or when too few numeric cells are present to draw conclusions.
    """

    numeric_rows = list(_iter_numeric_rows(rows))
    issues: List[ValidationIssue] = []
    checks_performed = 0
    checks_passed = 0

    # Row total checks – compare contiguous sections against total rows.
    running_totals: List[float] = []
    for row_index, (raw_row, numeric_row) in enumerate(zip(rows, numeric_rows)):
        label = _normalize(raw_row[0] if raw_row else "")
        if len(numeric_row) > len(running_totals):
            running_totals.extend([0.0] * (len(numeric_row) - len(running_totals)))

        if any(label_keyword in label for label_keyword in TOTAL_KEYWORDS):
            for column_index in range(1, len(numeric_row)):
                value = numeric_row[column_index]
                if value is None:
                    continue
                expected = running_totals[column_index]
                checks_performed += 1
                if math.isclose(value, expected, rel_tol=0.02, abs_tol=1.0):
                    checks_passed += 1
                else:
                    issues.append(
                        ValidationIssue(
                            message=(
                                f"Total in column {headers[column_index] if column_index < len(headers) else column_index}"
                                f" is {value} but expected {expected:.2f}"
                            ),
                            row=row_index,
                            column=column_index,
                        )
                    )
            running_totals = [0.0] * len(running_totals)
            continue

        if not label:
            running_totals = [0.0] * len(running_totals)
            continue

        if any(keyword in label for keyword in GROSS_PROFIT_KEYWORDS):
            # Derived rows like gross profit participate in reasonableness checks
            # but should not inflate running totals when we later hit a "total" row.
            continue

        for column_index in range(1, len(numeric_row)):
            value = numeric_row[column_index]
            if value is None:
                continue
            running_totals[column_index] += value

    # Reasonableness check: gross profit ≈ revenue - cogs per column.
    label_to_index: dict[str, int] = {}
    for idx, row in enumerate(rows):
        if not row:
            continue
        label_to_index[_normalize(row[0])] = idx

    revenue_idx = _first_matching_index(label_to_index, REVENUE_KEYWORDS)
    cogs_idx = _first_matching_index(label_to_index, COGS_KEYWORDS)
    gross_idx = _first_matching_index(label_to_index, GROSS_PROFIT_KEYWORDS)
    if revenue_idx is not None and cogs_idx is not None and gross_idx is not None:
        rev_row = numeric_rows[revenue_idx]
        cogs_row = numeric_rows[cogs_idx]
        gross_row = numeric_rows[gross_idx]
        for column_index in range(1, min(len(rev_row), len(cogs_row), len(gross_row))):
            rev = rev_row[column_index]
            cogs = cogs_row[column_index]
            gross = gross_row[column_index]
            if rev is None or cogs is None or gross is None:
                continue
            checks_performed += 1
            expected = rev + cogs if cogs < 0 else rev - cogs
            if math.isclose(gross, expected, rel_tol=0.03, abs_tol=1.5):
                checks_passed += 1
            else:
                issues.append(
                    ValidationIssue(
                        message=(
                            f"Gross profit {gross:.2f} does not match revenue minus COGS {expected:.2f}"
                        ),
                        row=gross_idx,
                        column=column_index,
                    )
                )

    numeric_cells = sum(1 for row in numeric_rows for value in row[1:] if value is not None)
    if numeric_cells == 0:
        issues.append(
            ValidationIssue(
                message="Table lacks numeric data to validate", severity="warning"
            )
        )
        confidence = 0.2
    else:
        if checks_performed == 0:
            confidence = 0.55
        else:
            confidence = max(0.1, min(0.99, checks_passed / checks_performed))
            # Reward robust tables with many successful checks.
            if checks_performed >= 3:
                confidence = min(0.99, confidence + 0.1)

    return TableValidationResult(confidence=round(confidence, 3), issues=issues)


def _first_matching_index(label_map: dict[str, int], keywords: Iterable[str]) -> Optional[int]:
    for keyword in keywords:
        for label, index in label_map.items():
            if keyword in label:
                return index
    return None


__all__ = [
    "TableValidationResult",
    "ValidationIssue",
    "parse_numeric",
    "validate_table",
]
