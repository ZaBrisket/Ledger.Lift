import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))

"""CAS hashing tests."""
import hashlib

import pytest

from apps.worker.services import cas
from apps.worker.services.cas import compute_pdf_hashes
from apps.worker.config import settings as worker_settings


def test_compute_pdf_hashes_returns_raw(monkeypatch):
    pdf_bytes = b"%PDF-1.4\n1 0 obj<<>>endobj"
    monkeypatch.setattr(worker_settings, "cas_normalize_pdf", False)
    hashes = compute_pdf_hashes(pdf_bytes)
    assert hashes.sha256_raw == hashlib.sha256(pdf_bytes).hexdigest()
    assert hashes.sha256_canonical is None


def test_compute_pdf_hashes_uses_qpdf_when_available(monkeypatch):
    pdf_bytes = b"%PDF-1.4\n1 0 obj<<>>endobj"
    monkeypatch.setattr(worker_settings, "cas_normalize_pdf", True)
    monkeypatch.setattr(cas.shutil, "which", lambda name: "/usr/bin/qpdf")

    def fake_qpdf(source, destination):
        destination.write_bytes(b"normalized")

    monkeypatch.setattr(cas, "_normalize_with_qpdf", fake_qpdf)

    def fail_pikepdf(*_args, **_kwargs):
        pytest.fail("pikepdf fallback should not run when qpdf succeeds")

    monkeypatch.setattr(cas, "_normalize_with_pikepdf", fail_pikepdf)

    hashes = compute_pdf_hashes(pdf_bytes)
    assert hashes.sha256_raw == hashlib.sha256(pdf_bytes).hexdigest()
    assert hashes.sha256_canonical == hashlib.sha256(b"normalized").hexdigest()


def test_compute_pdf_hashes_falls_back_when_qpdf_fails(monkeypatch):
    pdf_bytes = b"%PDF-1.4\n1 0 obj<<>>endobj"
    monkeypatch.setattr(worker_settings, "cas_normalize_pdf", True)
    monkeypatch.setattr(cas.shutil, "which", lambda name: "/usr/bin/qpdf" if name == "qpdf" else None)

    def failing_qpdf(*args, **kwargs):
        raise RuntimeError("boom")

    def fake_pikepdf(source, destination):
        destination.write_bytes(b"normalized-alt")

    monkeypatch.setattr(cas, "_normalize_with_qpdf", failing_qpdf)
    monkeypatch.setattr(cas, "_normalize_with_pikepdf", fake_pikepdf)

    hashes = compute_pdf_hashes(pdf_bytes)
    assert hashes.sha256_canonical == hashlib.sha256(b"normalized-alt").hexdigest()
