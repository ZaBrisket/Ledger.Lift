"""OCR provider abstraction with rate limiting and circuit breakers."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import List

from apps.worker.config import WorkerConfig, settings

from .rate_limit import CircuitBreaker, CircuitOpenError, RateLimiter

logger = logging.getLogger(__name__)


class OCRProviderError(RuntimeError):
    """Base class for provider-specific errors."""


class OCRConfigurationError(OCRProviderError):
    """Raised when provider configuration is invalid."""


class OCRRateLimitError(OCRProviderError):
    """Raised when a provider signals rate limiting."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class OCRTimeoutError(OCRProviderError):
    """Raised when provider execution exceeds the timeout."""


@dataclass(frozen=True)
class OCRCell:
    """Normalized representation of an OCR table cell."""

    page: int
    row: int
    column: int
    text: str
    is_numeric: bool
    numeric_value: float | None


class OCRProvider:
    """Protocol for OCR providers."""

    name: str

    def extract_cells(
        self,
        document_path: str,
        *,
        max_pages: int | None,
        timeout_ms: int | None,
    ) -> List[OCRCell]:  # pragma: no cover - Protocol
        raise NotImplementedError


def _parse_numeric_hint(text: str) -> tuple[bool, float | None]:
    cleaned = text.strip()
    if not cleaned:
        return False, None
    cleaned = cleaned.replace(",", "")
    if cleaned.endswith("%"):
        try:
            value = float(cleaned[:-1]) / 100
            return True, value
        except ValueError:
            return False, None
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    try:
        return True, float(cleaned)
    except ValueError:
        return False, None


class OCRRuntime:
    """Wraps a provider with rate limiting, backoff, and a circuit breaker."""

    def __init__(
        self,
        provider: OCRProvider,
        *,
        rate_limiter: RateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        max_retries: int = 3,
        backoff_initial: float = 1.0,
        backoff_max: float = 30.0,
        sleeper = time.sleep,
    ) -> None:
        self._provider = provider
        self._rate_limiter = rate_limiter
        self._circuit_breaker = circuit_breaker
        self._max_retries = max(0, max_retries)
        self._backoff_initial = max(0.1, backoff_initial)
        self._backoff_max = max(self._backoff_initial, backoff_max)
        self._sleep = sleeper

    @property
    def provider_name(self) -> str:
        return getattr(self._provider, "name", self._provider.__class__.__name__)

    def extract_cells(
        self,
        document_path: str,
        *,
        max_pages: int | None,
        timeout_ms: int | None,
    ) -> List[OCRCell]:
        if self._circuit_breaker:
            self._circuit_breaker.allow()

        if max_pages:
            _ensure_page_limit(document_path, max_pages=max_pages)

        attempt = 0
        delay = self._backoff_initial
        while True:
            if self._rate_limiter:
                self._rate_limiter.acquire()
            try:
                cells = self._provider.extract_cells(
                    document_path,
                    max_pages=max_pages,
                    timeout_ms=timeout_ms,
                )
            except OCRRateLimitError as exc:
                logger.warning("OCR provider %s throttled: %s", self.provider_name, exc)
                if self._circuit_breaker:
                    self._circuit_breaker.record_failure()
                if attempt >= self._max_retries:
                    raise
                backoff = exc.retry_after or delay
                backoff = min(backoff, self._backoff_max)
                logger.debug("Sleeping %.2fs before retry", backoff)
                self._sleep(backoff)
                delay = min(delay * 2, self._backoff_max)
                attempt += 1
                continue
            except CircuitOpenError:
                raise
            except Exception as exc:
                if self._circuit_breaker:
                    self._circuit_breaker.record_failure()
                raise
            else:
                if self._circuit_breaker:
                    self._circuit_breaker.record_success()
                return cells


def _ensure_page_limit(path: str, *, max_pages: int | None) -> None:
    if not max_pages:
        return
    try:
        import fitz  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency provided in runtime image
        raise OCRProviderError("PyMuPDF is required for page counting") from exc
    with fitz.open(path) as doc:  # type: ignore[attr-defined]
        if doc.page_count > max_pages:
            raise OCRProviderError(
                f"Document has {doc.page_count} pages which exceeds the configured limit of {max_pages}"
            )


def _build_rate_limiter(config: WorkerConfig) -> RateLimiter | None:
    provider = (config.ocr_provider or "").lower() if config.ocr_provider else None
    rate: float | None = None
    if provider == "textract":
        rate = float(config.ocr_tps_textract or 0)
    elif provider == "azure":
        rate = float(config.ocr_tps_azure or 0)
    if rate and rate > 0:
        return RateLimiter(rate_per_second=rate)
    return None


def _build_circuit_breaker(config: WorkerConfig) -> CircuitBreaker:
    cooldown = float(config.ocr_circuit_open_secs or 60)
    return CircuitBreaker(failure_threshold=3, recovery_time=cooldown)


def _require_feature(config: WorkerConfig) -> None:
    if not config.features_t2_ocr:
        raise OCRConfigurationError("T2 OCR feature flag is disabled")


def _make_provider(config: WorkerConfig) -> OCRProvider:
    provider = (config.ocr_provider or "").strip().lower()
    if not provider:
        raise OCRConfigurationError("OCR_PROVIDER must be set to azure, textract, or tesseract")
    if provider not in {"azure", "textract", "tesseract"}:
        raise OCRConfigurationError(f"Unsupported OCR provider: {provider}")
    if provider == "azure":
        from .azure_layout import AzureLayoutOCRProvider

        if not config.azure_di_endpoint or not config.azure_di_key:
            raise OCRConfigurationError("Azure Document Intelligence credentials are missing")
        return AzureLayoutOCRProvider(
            endpoint=config.azure_di_endpoint,
            api_key=config.azure_di_key,
        )
    if provider == "textract":
        from .aws_textract import AWSTextractOCRProvider

        if not config.aws_textract_region:
            raise OCRConfigurationError("AWS_TEXTRACT_REGION is required for Textract")
        return AWSTextractOCRProvider(
            region=config.aws_textract_region,
            access_key=config.aws_access_key_id,
            secret_key=config.aws_secret_access_key,
        )
    from .tesseract_local import TesseractLocalOCRProvider

    return TesseractLocalOCRProvider()


@lru_cache
def get_ocr_runtime(config: WorkerConfig | None = None) -> OCRRuntime:
    resolved_config = config or settings
    _require_feature(resolved_config)
    provider = _make_provider(resolved_config)
    limiter = _build_rate_limiter(resolved_config)
    breaker = _build_circuit_breaker(resolved_config)
    return OCRRuntime(
        provider,
        rate_limiter=limiter,
        circuit_breaker=breaker,
        max_retries=3,
        backoff_initial=1.0,
        backoff_max=resolved_config.ocr_circuit_open_secs or 60,
    )


__all__ = [
    "OCRCell",
    "OCRProvider",
    "OCRProviderError",
    "OCRConfigurationError",
    "OCRRateLimitError",
    "OCRTimeoutError",
    "OCRRuntime",
    "get_ocr_runtime",
    "_parse_numeric_hint",
]
