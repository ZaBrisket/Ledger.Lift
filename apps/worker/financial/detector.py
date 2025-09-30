"""Financial schedule detector combining structural and textual cues."""
from __future__ import annotations

import json
import logging
import os
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)

KEYWORD_MARKERS = {
    "revenue",
    "sales",
    "ebitda",
    "cogs",
    "cost of goods",
    "gross profit",
    "operating income",
    "operating loss",
    "net income",
    "net loss",
    "assets",
    "liabilities",
    "equity",
    "cash",
}

TOTAL_ROW_MARKERS = {
    "total",
    "net income",
    "net loss",
    "subtotal",
    "balance",
}

PERIOD_MARKERS = (
    r"q[1-4]",
    r"quarter",
    r"fy\s*20\d{2}",
    r"ytd",
    r"year\s*ended",
    r"\d{4}\s*-\s*\d{4}",
)

CURRENCY_SIGNS = {"$", "€", "£", "¥"}

DEFAULT_THRESHOLD = 0.5
LOW_CONFIDENCE_THRESHOLD = 0.3


@dataclass
class TableCandidate:
    """Structured table representation used by the detector."""

    headers: Sequence[str]
    rows: Sequence[Sequence[Optional[str]]]
    source: Optional[str] = None
    metadata: Optional[Dict[str, object]] = None

    @classmethod
    def from_records(cls, records: Sequence[Dict[str, object]]) -> "TableCandidate":
        if not records:
            return cls(headers=[], rows=[])
        keys = list(records[0].keys())
        rows = []
        for record in records:
            row = [str(record.get(key) or "") for key in keys]
            rows.append(row)
        return cls(headers=keys, rows=rows)


@dataclass
class FinancialDetectionResult:
    """Detection result and derived metadata."""

    score: float
    features: Dict[str, float]
    keyword_hits: List[str]
    is_financial: bool
    confidence: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "score": self.score,
                "features": self.features,
                "keyword_hits": self.keyword_hits,
                "is_financial": self.is_financial,
                "confidence": self.confidence,
            }
        )


class FinancialTableDetector:
    """Composite scoring detector for financial schedules."""

    def __init__(
        self,
        *,
        threshold: float = DEFAULT_THRESHOLD,
        low_confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
        use_ml: Optional[bool] = None,
        model_path: Optional[Path] = None,
    ) -> None:
        self.threshold = threshold
        self.low_confidence_threshold = low_confidence_threshold
        self.use_ml = self._should_enable_ml(use_ml)
        self.model_path = model_path or Path("assets/models/financial_t1_model.pkl")
        self._model = None

        if self.use_ml:
            self._load_or_train_model()

    def _should_enable_ml(self, explicit: Optional[bool]) -> bool:
        if explicit is not None:
            return explicit
        return os.getenv("FEATURES_T1_FINANCIAL_ML", "false").lower() == "true"

    def _load_or_train_model(self) -> None:
        try:  # pragma: no cover - exercised in optional integration test
            from sklearn.linear_model import LogisticRegression
            import joblib
        except Exception as exc:  # pragma: no cover - optional dependency guard
            logger.warning("Financial ML detector unavailable: %s", exc)
            self.use_ml = False
            return

        fixture_path = Path("apps/worker/tests/fixtures/financial_tables.json")
        if not fixture_path.exists():
            logger.warning("Financial detector fixture missing: skipping ML model")
            self.use_ml = False
            return

        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        if self.model_path.exists():
            try:
                self._model = joblib.load(self.model_path)
                return
            except Exception as exc:  # pragma: no cover - corrupted model guard
                logger.warning("Failed to load cached model: %s", exc)

        with fixture_path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)

        X: List[List[float]] = []
        y: List[int] = []
        for item in payload:
            candidate = TableCandidate(headers=item["headers"], rows=item["rows"])
            features = self._extract_feature_vector(candidate)
            X.append([features[key] for key in sorted(features)])
            y.append(1 if item["label"] == "financial" else 0)

        if not X:
            logger.warning("Financial detector fixture empty: skipping ML model")
            self.use_ml = False
            return

        model = LogisticRegression(max_iter=200)
        model.fit(X, y)
        joblib.dump(model, self.model_path)
        self._model = model

    def score(self, candidate: TableCandidate) -> FinancialDetectionResult:
        features = self._extract_feature_vector(candidate)
        keyword_hits = self._collect_keyword_hits(candidate)
        base_score = self._combine_features(features, keyword_hits)

        if self.use_ml and self._model is not None:  # pragma: no cover - optional
            try:
                ordered_features = [features[key] for key in sorted(features)]
                base_score = float(self._model.predict_proba([ordered_features])[0][1])
            except Exception as exc:
                logger.warning("Financial ML scoring failed: %s", exc)

        confidence = "high" if base_score >= self.threshold else (
            "medium" if base_score >= self.low_confidence_threshold else "low"
        )
        return FinancialDetectionResult(
            score=base_score,
            features=features,
            keyword_hits=keyword_hits,
            is_financial=base_score >= self.low_confidence_threshold,
            confidence=confidence,
        )

    def _extract_feature_vector(self, candidate: TableCandidate) -> Dict[str, float]:
        headers = [self._normalize_cell(cell) for cell in candidate.headers]
        rows = [
            [self._normalize_cell(cell) for cell in row]
            for row in candidate.rows
        ]

        numeric_density_header = self._numeric_density(headers)
        numeric_density_body = (
            statistics.fmean(self._numeric_density(row) for row in rows)
            if rows
            else 0.0
        )
        density_gradient = max(0.0, numeric_density_body - numeric_density_header)

        column_stability = self._column_count_stability(headers, rows)
        indentation = self._indentation_score(rows)
        periodized = self._periodized_column_score(headers)
        totals = self._total_row_score(rows)
        currency = self._currency_score(rows)

        return {
            "column_stability": column_stability,
            "density_gradient": density_gradient,
            "indentation": indentation,
            "periodized": periodized,
            "totals": totals,
            "currency": currency,
        }

    def _combine_features(self, features: Dict[str, float], keyword_hits: Iterable[str]) -> float:
        weights = {
            "column_stability": 0.15,
            "density_gradient": 0.2,
            "indentation": 0.1,
            "periodized": 0.2,
            "totals": 0.15,
            "currency": 0.1,
            "keywords": 0.1,
        }
        weighted = sum(features[name] * weight for name, weight in weights.items() if name in features)
        keyword_bonus = min(1.0, len(list(keyword_hits)) / 5.0)
        weighted += weights["keywords"] * keyword_bonus
        return max(0.0, min(1.0, weighted))

    def _collect_keyword_hits(self, candidate: TableCandidate) -> List[str]:
        hits: List[str] = []
        cells = list(candidate.headers)
        for row in candidate.rows:
            cells.extend(row)
        for cell in cells:
            normalized = self._normalize_cell(cell)
            for keyword in KEYWORD_MARKERS:
                if keyword in normalized:
                    hits.append(keyword)
                    break
            if any(sign in str(cell) for sign in CURRENCY_SIGNS):
                hits.append("currency")
            if "(" in str(cell) and ")" in str(cell):
                hits.append("parentheses")
        return hits

    def _normalize_cell(self, cell: Optional[object]) -> str:
        if cell is None:
            return ""
        return str(cell).strip().lower()

    def _numeric_density(self, row: Sequence[str]) -> float:
        if not row:
            return 0.0
        numeric_cells = 0
        for cell in row:
            cell = cell or ""
            if any(ch.isdigit() for ch in cell):
                numeric_cells += 1
        return numeric_cells / len(row)

    def _column_count_stability(self, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> float:
        header_cols = len([cell for cell in headers if cell]) or len(headers)
        if not rows:
            return 0.0
        body_lengths = [len([cell for cell in row if cell]) or len(row) for row in rows if row]
        if not body_lengths:
            return 0.0
        avg_body = statistics.mean(body_lengths)
        variance = statistics.pvariance(body_lengths) if len(body_lengths) > 1 else 0.0
        if header_cols == 0:
            return 0.0
        stability = 1.0 - min(1.0, abs(avg_body - header_cols) / max(header_cols, 1))
        stability *= 1.0 - min(1.0, variance / (max(header_cols, 1) ** 2))
        return max(0.0, min(1.0, stability))

    def _indentation_score(self, rows: Sequence[Sequence[str]]) -> float:
        if not rows:
            return 0.0
        indent_levels: List[int] = []
        for row in rows:
            if not row:
                continue
            first_cell = row[0] or ""
            indent = len(first_cell) - len(first_cell.lstrip())
            bullet = first_cell.count("·") + first_cell.count("-")
            indent_levels.append(min(4, indent + bullet))
        if not indent_levels:
            return 0.0
        unique_levels = len(set(indent_levels))
        return min(1.0, unique_levels / 4.0)

    def _periodized_column_score(self, headers: Sequence[str]) -> float:
        if not headers:
            return 0.0
        import re

        matches = 0
        for header in headers:
            header_norm = self._normalize_cell(header)
            for pattern in PERIOD_MARKERS:
                if re.search(pattern, header_norm):
                    matches += 1
                    break
        return min(1.0, matches / max(1, len(headers)))

    def _total_row_score(self, rows: Sequence[Sequence[str]]) -> float:
        if not rows:
            return 0.0
        last_rows = rows[-3:]
        hits = 0
        for row in last_rows:
            for cell in row:
                normalized = self._normalize_cell(cell)
                if not normalized:
                    continue
                if any(marker in normalized for marker in TOTAL_ROW_MARKERS):
                    hits += 1
                    break
        return min(1.0, hits / max(1, len(last_rows)))

    def _currency_score(self, rows: Sequence[Sequence[str]]) -> float:
        if not rows:
            return 0.0
        total_cells = sum(len(row) for row in rows) or 1
        currency_cells = 0
        negative_paren = 0
        for row in rows:
            for cell in row:
                text = str(cell or "")
                if any(symbol in text for symbol in CURRENCY_SIGNS):
                    currency_cells += 1
                if "(" in text and ")" in text and any(ch.isdigit() for ch in text):
                    negative_paren += 1
        density = currency_cells / total_cells
        negative_bonus = min(0.5, negative_paren / max(1, len(rows)))
        return max(0.0, min(1.0, density + negative_bonus))


__all__ = [
    "FinancialTableDetector",
    "FinancialDetectionResult",
    "TableCandidate",
]
