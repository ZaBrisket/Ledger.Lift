"""Tests for OCR rate limiting and circuit breakers."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))

import pytest

from apps.worker.ocr import OCRCell, OCRRateLimitError, OCRRuntime
from apps.worker.ocr.rate_limit import CircuitBreaker, CircuitOpenError, RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, delta: float) -> None:
        self.value += delta


def test_rate_limiter_token_bucket_throttles() -> None:
    clock = FakeClock()
    sleeps: list[float] = []

    def fake_sleep(duration: float) -> None:
        sleeps.append(duration)
        clock.advance(duration)

    limiter = RateLimiter(rate_per_second=2, clock=clock, sleeper=fake_sleep)
    limiter.acquire()
    limiter.acquire()
    limiter.acquire()

    assert sleeps == [0.5]


def test_circuit_breaker_opens_and_recovers() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=2, recovery_time=10, clock=clock)

    breaker.allow()
    breaker.record_failure()
    breaker.record_failure()

    with pytest.raises(CircuitOpenError):
        breaker.allow()

    clock.advance(9)
    with pytest.raises(CircuitOpenError):
        breaker.allow()

    clock.advance(1)
    breaker.allow()
    assert breaker.state == "half_open"

    breaker.record_success()
    assert breaker.state == "closed"


def test_runtime_backoff_and_circuit(tmp_path) -> None:
    clock = FakeClock()
    sleeps: list[float] = []

    def fake_sleep(duration: float) -> None:
        sleeps.append(round(duration, 2))
        clock.advance(duration)

    class FlakyProvider:
        name = "stub"

        def __init__(self) -> None:
            self.calls = 0

        def extract_cells(self, document_path: str, *, max_pages: int | None, timeout_ms: int | None):
            self.calls += 1
            if self.calls == 1:
                raise OCRRateLimitError("slow", retry_after=0.5)
            if self.calls == 2:
                raise OCRRateLimitError("still slow")
            return [
                OCRCell(page=1, row=0, column=0, text="ok", is_numeric=False, numeric_value=None)
            ]

    provider = FlakyProvider()
    limiter = RateLimiter(rate_per_second=10, clock=clock, sleeper=fake_sleep)
    breaker = CircuitBreaker(failure_threshold=3, recovery_time=30, clock=clock)
    runtime = OCRRuntime(
        provider,
        rate_limiter=limiter,
        circuit_breaker=breaker,
        backoff_initial=0.5,
        backoff_max=2.0,
        sleeper=fake_sleep,
    )

    document_path = tmp_path / "doc.pdf"
    document_path.write_bytes(b"test")

    result = runtime.extract_cells(str(document_path), max_pages=None, timeout_ms=1000)

    assert provider.calls == 3
    assert result[0].text == "ok"
    assert sleeps == [0.5, 1.0]
    assert breaker.state == "closed"
