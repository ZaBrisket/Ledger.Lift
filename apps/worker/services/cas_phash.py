"""Perceptual hashing helpers for CAS deduplication."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence, TYPE_CHECKING, Any

import fitz  # type: ignore

try:  # pragma: no cover - optional dependency guard
    from PIL import Image  # type: ignore
except ImportError as pillow_error:  # pragma: no cover - exercised when Pillow missing
    Image = None  # type: ignore[assignment]
    _PIL_IMPORT_ERROR = pillow_error
else:  # pragma: no cover - dependency available
    _PIL_IMPORT_ERROR = None

try:  # pragma: no cover - optional dependency guard
    from imagehash import ImageHash, hex_to_hash, phash  # type: ignore
except ImportError as imagehash_error:  # pragma: no cover - exercised when imagehash missing
    ImageHash = None  # type: ignore[assignment]
    hex_to_hash = None  # type: ignore[assignment]
    phash = None  # type: ignore[assignment]
    _IMAGEHASH_IMPORT_ERROR = imagehash_error
else:  # pragma: no cover - dependency available
    _IMAGEHASH_IMPORT_ERROR = None

if TYPE_CHECKING:  # pragma: no cover - typing helper
    from PIL.Image import Image as PILImageType
else:  # pragma: no cover - runtime fallback
    PILImageType = Any

logger = logging.getLogger(__name__)

PHASH_KEY_PREFIX = "cas:phash"


@dataclass(frozen=True)
class CASPhashResult:
    """Computed perceptual hashes for the first rendered pages."""

    hashes: Sequence[str]
    pages_processed: int

    def as_list(self) -> List[str]:
        return list(self.hashes)


def ensure_phash_support() -> None:
    """Raise an informative error when pHash dependencies are unavailable."""

    if Image is None:
        raise ImportError(
            "Pillow is required for CAS pHash deduplication. Install ledger-lift-worker[phash]."
        ) from _PIL_IMPORT_ERROR

    if any(dependency is None for dependency in (ImageHash, hex_to_hash, phash)):
        raise ImportError(
            "imagehash is required for CAS pHash deduplication. Install ledger-lift-worker[phash]."
        ) from _IMAGEHASH_IMPORT_ERROR


def _render_page(doc: fitz.Document, page_index: int) -> Optional["PILImageType"]:
    """Render a PDF page to a Pillow image."""

    try:
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        mode = "RGBA" if pix.alpha else "RGB"
        image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
        if mode == "RGBA":
            image = image.convert("RGB")
        return image
    except Exception as exc:  # pragma: no cover - defensive guard for corrupt pages
        logger.warning("Failed to render page %s for pHash: %s", page_index, exc)
        return None


def compute_pdf_phashes(pdf_bytes: bytes, *, max_pages: int = 3) -> CASPhashResult:
    """Compute perceptual hashes for the first ``max_pages`` pages of a PDF."""

    if max_pages <= 0:
        return CASPhashResult(hashes=(), pages_processed=0)

    ensure_phash_support()

    hashes: List[str] = []
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            page_count = min(len(doc), max_pages)
            for page_index in range(page_count):
                image = _render_page(doc, page_index)
                if image is None:
                    continue
                hash_value = phash(image)
                hashes.append(str(hash_value))
    except Exception as exc:  # pragma: no cover - corrupted PDF defensive guard
        logger.warning("Failed to compute pHash: %s", exc)
        return CASPhashResult(hashes=tuple(hashes), pages_processed=len(hashes))

    return CASPhashResult(hashes=tuple(hashes), pages_processed=len(hashes))


def phash_distance(hash_a: str, hash_b: str) -> int:
    """Return the Hamming distance between two perceptual hash hex strings."""

    ensure_phash_support()

    try:
        return abs(hex_to_hash(hash_a) - hex_to_hash(hash_b))
    except Exception as exc:  # pragma: no cover - invalid hash defensive guard
        logger.debug("Failed to compute pHash distance: %s", exc)
        return 64


def _doc_key(document_id: str) -> str:
    return f"{PHASH_KEY_PREFIX}:doc:{document_id}"


def _page_key(page_index: int, hash_hex: str) -> str:
    return f"{PHASH_KEY_PREFIX}:page:{page_index}:{hash_hex}"


def store_pdf_phashes(connection, document_id: str, hashes: Sequence[str]) -> None:
    """Persist pHashes in Redis for future deduplication."""

    if not hashes:
        return

    mapping = {str(idx): value for idx, value in enumerate(hashes)}
    pipeline = getattr(connection, "pipeline", None)

    if callable(pipeline):
        pipe = pipeline()
    else:
        pipe = None

    executor = pipe or connection

    executor.hset(_doc_key(document_id), mapping=mapping)
    for idx, hash_hex in enumerate(hashes):
        executor.sadd(_page_key(idx, hash_hex), document_id)

    if pipe is not None:
        pipe.execute()


def _decode(value: bytes | str | None) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _collect_candidate_ids(connection, hashes: Sequence[str]) -> set[str]:
    candidates: set[str] = set()
    for page_index, hash_hex in enumerate(hashes):
        key = _page_key(page_index, hash_hex)
        try:
            page_candidates = connection.smembers(key)
        except Exception as exc:  # pragma: no cover - redis runtime guard
            logger.debug("Failed to read pHash candidates: %s", exc)
            continue
        for candidate in page_candidates or []:
            candidate_id = _decode(candidate)
            if candidate_id:
                candidates.add(candidate_id)
    return candidates


def _load_candidate_hashes(connection, document_id: str) -> List[str]:
    try:
        stored = connection.hgetall(_doc_key(document_id))
    except Exception as exc:  # pragma: no cover - redis runtime guard
        logger.debug("Failed to fetch pHash record for %s: %s", document_id, exc)
        return []

    if not stored:
        return []

    decoded: dict[int, str] = {}
    for raw_key, value in stored.items():
        try:
            if isinstance(raw_key, bytes):
                index = int(raw_key.decode("utf-8"))
            else:
                index = int(raw_key)
        except (TypeError, ValueError):
            continue
        decoded[index] = _decode(value) or ""

    if not decoded:
        return []

    max_index = max(decoded.keys())
    return [decoded.get(index, "") for index in range(max_index + 1)]


def _hashes_within_threshold(
    target_hashes: Sequence[str],
    candidate_hashes: Sequence[str],
    *,
    distance_max: int,
) -> bool:
    if not candidate_hashes:
        return False

    compare_count = min(len(target_hashes), len(candidate_hashes))
    if compare_count == 0:
        return False

    for idx in range(compare_count):
        distance = phash_distance(target_hashes[idx], candidate_hashes[idx])
        if distance > distance_max:
            return False
    return True


def find_duplicate_by_phash(
    connection,
    hashes: Sequence[str],
    *,
    distance_max: int,
    exclude_document_id: Optional[str] = None,
) -> Optional[str]:
    """Return the document id of a near-duplicate PDF if one is indexed."""

    if not hashes:
        return None

    candidate_ids = _collect_candidate_ids(connection, hashes)
    if exclude_document_id:
        candidate_ids.discard(exclude_document_id)

    for candidate in candidate_ids:
        candidate_hashes = _load_candidate_hashes(connection, candidate)
        if _hashes_within_threshold(hashes, candidate_hashes, distance_max=distance_max):
            return candidate
    return None


__all__ = [
    "CASPhashResult",
    "ensure_phash_support",
    "compute_pdf_phashes",
    "find_duplicate_by_phash",
    "phash_distance",
    "store_pdf_phashes",
]
