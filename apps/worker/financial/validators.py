"""Numeric table validators for financial schedules."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Literal, Optional, Sequence

REVIEW_CONFIDENCE_THRESHOLD = float(
    os.getenv("REVIEW_CONFIDENCE_THRESHOLD", "0.6")
)

TOTAL_KEYWORDS = {
    "total",
    "subtotal",
    "net income",
    "net loss",
    "balance",
}

NEGATIVE_PAREN_PATTERN = re.compile(r"^\s*\((.+)\)\s*$")
PERCENT_PATTERN = re.compile(r"%$")
NUMERIC_CLEAN_PATTERN = re.compile(r"[^0-9.\-]")


@dataclass
class ParsedCell:
    raw: Optional[str]
    value: Optional[float]
    is_numeric: bool
    normalized: str


@dataclass
class ValidationIssue:
    code: str
    message: str
    row: Optional[int] = None
    column: Optional[int] = None
    expected: Optional[float] = None
    actual: Optional[float] = None
    severity: Literal["critical", "error", "warning", "info"] = "error"


@dataclass
class TableValidationResult:
    issues: List[ValidationIssue]
    confidence: float
    numeric_cells: int
    parsed_cells: int

    @property
    def low_confidence(self) -> bool:
        if self.confidence < REVIEW_CONFIDENCE_THRESHOLD:
            return True
        return any(issue.severity in {"critical", "error"} for issue in self.issues)


def _coerce_numeric(token: Optional[str]) -> ParsedCell:
    if token is None:
        return ParsedCell(raw=None, value=None, is_numeric=False, normalized="")

    stripped = token.strip()
    if not stripped:
        return ParsedCell(raw=token, value=None, is_numeric=False, normalized="")

    lower = stripped.lower()
    if lower in {"n/a", "na", "--"}:
        return ParsedCell(raw=token, value=None, is_numeric=False, normalized=lower)

    percent = "%" in stripped
    if percent:
        stripped = stripped.replace("%", "")

    negative_match = NEGATIVE_PAREN_PATTERN.match(stripped)
    negative = False
    if negative_match:
        negative = True
        stripped = negative_match.group(1)

    cleaned = NUMERIC_CLEAN_PATTERN.sub("", stripped)
    if cleaned.count(".") > 1:
        return ParsedCell(raw=token, value=None, is_numeric=False, normalized=cleaned)

    try:
        value = float(cleaned) if cleaned else None
    except ValueError:
        return ParsedCell(raw=token, value=None, is_numeric=False, normalized=cleaned)

    if value is None:
        return ParsedCell(raw=token, value=None, is_numeric=False, normalized=cleaned)

    if percent:
        value /= 100.0

    if negative:
        value *= -1

    return ParsedCell(raw=token, value=value, is_numeric=True, normalized=cleaned)
def _normalize_label(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _numeric_columns(rows: Sequence[Sequence[ParsedCell]]) -> List[int]:
    if not rows:
        return []
    column_count = max(len(row) for row in rows)
    numeric_columns: List[int] = []
    for col in range(column_count):
        numeric_count = 0
        for row in rows:
            if col < len(row) and row[col].is_numeric and row[col].value is not None:
                numeric_count += 1
        if numeric_count >= 2:
            numeric_columns.append(col)
    return numeric_columns


def _sum_column(rows: Sequence[Sequence[ParsedCell]], column: int, *, end: int) -> Optional[float]:
    values: List[float] = []
    for row_index in range(end):
        row = rows[row_index]
        if row and any(keyword in _normalize_label(row[0].raw) for keyword in TOTAL_KEYWORDS):
            continue
        if column < len(row) and row[column].value is not None:
            values.append(row[column].value)  # type: ignore[arg-type]
    if not values:
        return None
    return float(sum(values))


def _within_tolerance(expected: float, actual: float) -> bool:
    if expected == actual:
        return True
    tolerance = max(0.01, abs(expected) * 0.01)
    return abs(expected - actual) <= tolerance


def _validate_totals(rows: Sequence[Sequence[ParsedCell]]) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    numeric_cols = _numeric_columns(rows)
    for idx, row in enumerate(rows):
        if not row:
            continue
        label = _normalize_label(row[0].raw if row else None)
        if not label:
            continue
        if any(keyword in label for keyword in TOTAL_KEYWORDS):
            for column in numeric_cols:
                if column >= len(row):
                    continue
                cell = row[column]
                if not cell.is_numeric or cell.value is None:
                    continue
                expected = _sum_column(rows, column, end=idx)
                if expected is None:
                    continue
                if not _within_tolerance(expected, cell.value):
                    issues.append(
                        ValidationIssue(
                            code="total.mismatch",
                            message=f"Column {column} total {cell.value} does not match computed sum {expected}",
                            row=idx,
                            column=column,
                            expected=expected,
                            actual=cell.value,
                            severity="error",
                        )
                    )
    return issues


def _validate_reasonableness(rows: Sequence[Sequence[ParsedCell]]) -> List[ValidationIssue]:
    label_map: dict[str, Sequence[ParsedCell]] = {}
    for row in rows:
        if not row:
            continue
        label_map[_normalize_label(row[0].raw if row else None)] = row

    revenue = label_map.get("revenue")
    cogs = label_map.get("cogs") or label_map.get("cost of goods sold")
    gross = label_map.get("gross profit")

    if revenue and cogs and gross:
        issues: List[ValidationIssue] = []
        column_count = min(len(revenue), len(cogs), len(gross))
        for column in range(1, column_count):
            r_cell = revenue[column]
            c_cell = cogs[column]
            g_cell = gross[column]
            if (
                r_cell.value is None
                or c_cell.value is None
                or g_cell.value is None
            ):
                continue
            expected = r_cell.value - c_cell.value
            if not _within_tolerance(expected, g_cell.value):
                issues.append(
                    ValidationIssue(
                        code="reasonableness.gross_profit",
                        message="Gross profit does not equal revenue minus COGS",
                        row=None,
                        column=column,
                        expected=expected,
                        actual=g_cell.value,
                        severity="error",
                    )
                )
        return issues
    return []


def validate_numeric_table(table: Sequence[Sequence[Optional[str]]]) -> TableValidationResult:
    """Validate a 2-D table of strings and compute confidence."""
    parsed_rows: List[List[ParsedCell]] = [
        [_coerce_numeric(cell) for cell in row]
        for row in table
    ]
    issues = _validate_totals(parsed_rows)
    issues.extend(_validate_reasonableness(parsed_rows))

    numeric_cells = sum(cell.is_numeric for row in parsed_rows for cell in row)
    parsed_cells = sum(1 for row in parsed_rows for cell in row)

    confidence_penalty = 0.0
    if parsed_cells:
        confidence_penalty += 0.2 * (1 - (numeric_cells / parsed_cells))
    confidence_penalty += min(0.6, 0.15 * len(issues))
    base_confidence = 1.0 - confidence_penalty
    confidence = max(0.0, round(base_confidence, 3))

    return TableValidationResult(
        issues=issues,
        confidence=confidence,
        numeric_cells=numeric_cells,
        parsed_cells=parsed_cells,
    )


__all__ = [
    "ParsedCell",
    "ValidationIssue",
    "TableValidationResult",
    "validate_numeric_table",
]
