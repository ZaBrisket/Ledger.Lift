import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))

from apps.worker.config import WorkerConfig
from apps.worker.ocr.select import (
    DocumentTraits,
    ProviderDecision,
    auto_select_provider,
    resolve_provider_name,
    select_provider,
)


def make_config() -> WorkerConfig:
    return WorkerConfig(
        ocr_provider_mode="auto",
        ocr_provider="textract",
        features_t2_ocr=True,
        aws_textract_region="us-east-1",
        azure_di_endpoint="https://example",
        azure_di_key="key",
    )


def test_handles_malformed_metadata() -> None:
    traits = DocumentTraits(page_count=5, raster_ratio=0.3, table_merges=1)
    metadata = {
        "page_count": "40 pages",
        "raster_ratio": "75%",
        "table_merge_count": "unknown",
        "offline": "false",
    }

    decision = select_provider(traits, metadata=metadata)

    assert isinstance(decision, ProviderDecision)
    assert decision.provider in {"azure", "textract", "tesseract"}

    provider = auto_select_provider(metadata)
    assert provider in {"azure", "textract", "tesseract"}


def test_resolve_provider_returns_decision() -> None:
    config = make_config()
    provider, decision = resolve_provider_name(
        config,
        metadata={"raster_ratio": "80%", "page_count": "5"},
    )

    assert provider in {"textract", "azure", "tesseract"}
    assert isinstance(decision, ProviderDecision)
    assert decision.reason in {
        "preferred-provider",
        "cost-sensitive",
        "high-raster-ratio",
        "moderate-raster",
        "structured-form",
        "default-structured",
        "long-document-low-raster",
    }
