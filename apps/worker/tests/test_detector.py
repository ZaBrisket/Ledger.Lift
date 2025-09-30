import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))

"""Unit tests for financial detector structural scoring."""
from apps.worker.financial import FinancialTableDetector, TableCandidate


def build_financial_candidate() -> TableCandidate:
    return TableCandidate(
        headers=["", "Q1 2023", "Q2 2023", "FY 2023"],
        rows=[
            ["Revenue", "$1,200", "$1,400", "$5,600"],
            ["Cost of Goods Sold", "(500)", "(600)", "(2,200)"],
            ["Gross Profit", "$700", "$800", "$3,400"],
            ["Operating Income", "$200", "$250", "$1,000"],
            ["Net Income", "$150", "$200", "$850"],
        ],
    )


def build_generic_candidate() -> TableCandidate:
    return TableCandidate(
        headers=["Task", "Owner", "Status"],
        rows=[
            ["Update homepage", "Alice", "In Progress"],
            ["Email campaign", "Bob", "Queued"],
            ["Customer interviews", "Eve", "Done"],
        ],
    )


def test_financial_candidate_scores_high():
    detector = FinancialTableDetector()
    result = detector.score(build_financial_candidate())

    assert result.score >= detector.threshold
    assert result.is_financial
    assert result.confidence == "high"
    assert result.features["periodized"] > 0
    assert "revenue" in result.keyword_hits


def test_generic_candidate_scores_low():
    detector = FinancialTableDetector()
    result = detector.score(build_generic_candidate())

    assert result.score < detector.low_confidence_threshold
    assert not result.is_financial
    assert result.confidence == "low"


def test_low_confidence_band():
    detector = FinancialTableDetector(threshold=0.7, low_confidence_threshold=0.3)
    borderline = TableCandidate(
        headers=["Metric", "Q1 2023", "Q2 2023"],
        rows=[
            ["Subscriptions", "1200", "1350"],
            ["Support", "400", "420"],
            ["Total", "1600", "1770"],
        ],
    )

    result = detector.score(borderline)
    assert result.confidence == "medium"
