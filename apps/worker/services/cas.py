"""Content-addressable storage helpers."""
from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from apps.worker.config import settings

logger = logging.getLogger(__name__)


@dataclass
class CASHashes:
    sha256_raw: str
    sha256_canonical: Optional[str]


def _hash_bytes(data: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()


def _normalize_with_qpdf(source: Path, destination: Path) -> None:
    subprocess.run(
        ["qpdf", "--deterministic-id", str(source), str(destination)],
        check=True,
        capture_output=True,
    )


def _normalize_with_pikepdf(source: Path, destination: Path) -> None:
    try:  # pragma: no cover - optional dependency
        import pikepdf
    except ImportError as exc:  # pragma: no cover - optional
        raise RuntimeError("pikepdf not installed") from exc

    with pikepdf.open(source) as pdf:
        pdf.save(destination, linearize=True, fix_metadata_version=True)


def _canonicalize_pdf(pdf_bytes: bytes) -> Optional[bytes]:
    if not settings.cas_normalize_pdf:
        return None

    has_qpdf = shutil.which("qpdf") is not None

    with tempfile.TemporaryDirectory(prefix="ledger_cas_") as tmpdir:
        source = Path(tmpdir) / "source.pdf"
        dest = Path(tmpdir) / "normalized.pdf"
        source.write_bytes(pdf_bytes)

        if has_qpdf:
            try:
                _normalize_with_qpdf(source, dest)
                return dest.read_bytes()
            except Exception as exc:  # pragma: no cover - best effort
                logger.warning("qpdf normalization failed: %s", exc)

        try:  # fallback to pikepdf if available
            _normalize_with_pikepdf(source, dest)
            return dest.read_bytes()
        except Exception as exc:  # pragma: no cover
            logger.warning("pikepdf normalization failed: %s", exc)
            return None


def compute_pdf_hashes(pdf_bytes: bytes) -> CASHashes:
    """Compute raw and canonical SHA-256 hashes for a PDF."""

    sha_raw = _hash_bytes(pdf_bytes)
    canonical_bytes = _canonicalize_pdf(pdf_bytes)
    sha_canonical = _hash_bytes(canonical_bytes) if canonical_bytes else None
    return CASHashes(sha256_raw=sha_raw, sha256_canonical=sha_canonical)


__all__ = ["CASHashes", "compute_pdf_hashes"]
