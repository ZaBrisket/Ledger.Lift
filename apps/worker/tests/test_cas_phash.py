import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))

"""Tests for perceptual hashing utilities."""

from typing import Dict, Set

import fitz  # type: ignore
import pytest

pytest.importorskip("imagehash")
pytest.importorskip("PIL.Image")

from apps.worker.services.cas_phash import (
    CASPhashResult,
    compute_pdf_phashes,
    find_duplicate_by_phash,
    phash_distance,
    store_pdf_phashes,
)


class FakeRedis:
    """Minimal Redis-like store for unit testing."""

    def __init__(self):
        self.hashes: Dict[str, Dict[str, str]] = {}
        self.sets: Dict[str, Set[str]] = {}

    def pipeline(self):  # pragma: no cover - exercised indirectly
        return self

    def hset(self, key: str, mapping: Dict[str, str]):
        self.hashes.setdefault(key, {}).update(mapping)

    def sadd(self, key: str, value: str):
        self.sets.setdefault(key, set()).add(value)

    def execute(self):  # pragma: no cover - provided for pipeline API compatibility
        return []

    def smembers(self, key: str):
        return {member.encode("utf-8") for member in self.sets.get(key, set())}

    def hgetall(self, key: str):
        stored = self.hashes.get(key, {})
        return {k.encode("utf-8"): v.encode("utf-8") for k, v in stored.items()}


@pytest.fixture
def sample_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Sample Report")
    metadata = doc.metadata
    metadata["producer"] = "LedgerLift"
    doc.set_metadata(metadata)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def similar_pdf(sample_pdf: bytes) -> bytes:
    with fitz.open(stream=sample_pdf, filetype="pdf") as original:
        clone = fitz.open()
        for page_index in range(len(original)):
            page = clone.new_page()
            page.show_pdf_page(page.rect, original, page_index)
        metadata = clone.metadata
        metadata["producer"] = "AnotherProducer"
        metadata["title"] = "Updated title"
        clone.set_metadata(metadata)
        result = clone.tobytes()
        clone.close()
    return result


def test_compute_pdf_phashes_returns_pages(sample_pdf: bytes):
    result = compute_pdf_phashes(sample_pdf, max_pages=3)
    assert isinstance(result, CASPhashResult)
    assert result.hashes
    assert result.pages_processed == len(result.hashes)


def test_phash_distance_with_metadata_change(sample_pdf: bytes, similar_pdf: bytes):
    first = compute_pdf_phashes(sample_pdf)
    second = compute_pdf_phashes(similar_pdf)
    assert first.hashes and second.hashes
    assert phash_distance(first.hashes[0], second.hashes[0]) == 0


def test_find_duplicate_by_phash_matches(sample_pdf: bytes, similar_pdf: bytes):
    store = FakeRedis()
    original = compute_pdf_phashes(sample_pdf)
    store_pdf_phashes(store, "doc-1", original.hashes)

    duplicate = compute_pdf_phashes(similar_pdf)
    doc_id = find_duplicate_by_phash(store, duplicate.hashes, distance_max=6, exclude_document_id="doc-2")
    assert doc_id == "doc-1"


def test_find_duplicate_by_phash_respects_threshold(sample_pdf: bytes):
    store = FakeRedis()
    original = compute_pdf_phashes(sample_pdf)
    store_pdf_phashes(store, "doc-1", original.hashes)

    blank_doc = fitz.open()
    page = blank_doc.new_page()
    page.insert_text((72, 72), "Totally different content")
    mutated_pdf = blank_doc.tobytes()
    blank_doc.close()

    mutated_hashes = compute_pdf_phashes(mutated_pdf).hashes
    doc_id = find_duplicate_by_phash(store, mutated_hashes, distance_max=0)
    assert doc_id is None
