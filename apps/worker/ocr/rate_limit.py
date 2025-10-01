"""Rate limiting and circuit breaker utilities for OCR providers."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


class CircuitOpenError(RuntimeError):
    """Raised when a circuit breaker denies work."""


@dataclass
class _TokenBucket:
    """Simple token bucket implementation."""

    rate_per_second: float
    capacity: float
    clock: Callable[[], float]

    tokens: float = 0.0
    updated_at: float | None = None

    def __post_init__(self) -> None:
        if self.rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        self.capacity = max(self.capacity, 1.0)
        if self.updated_at is None:
            self.updated_at = self.clock()
        self.tokens = self.capacity

    def _refill(self) -> None:
        now = self.clock()
        assert self.updated_at is not None
        elapsed = max(0.0, now - self.updated_at)
        if elapsed <= 0:
            return
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_second)
        self.updated_at = now

    def consume(self, tokens: float = 1.0) -> float:
        """Consume tokens and return the wait duration if throttled."""

        if tokens <= 0:
            return 0.0
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return 0.0
        deficit = tokens - self.tokens
        wait_time = deficit / self.rate_per_second
        self.tokens = max(0.0, self.tokens - tokens)
        self.updated_at = self.clock()
        return max(0.0, wait_time)


class RateLimiter:
    """Token bucket rate limiter with optional sleeping."""

    def __init__(
        self,
        rate_per_second: float | None,
        capacity: float | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._clock = clock
        self._sleeper = sleeper
        self._bucket = (
            _TokenBucket(rate_per_second, capacity or rate_per_second or 1.0, clock)
            if rate_per_second and rate_per_second > 0
            else None
        )

    def acquire(self, tokens: float = 1.0) -> None:
        """Acquire the requested tokens, sleeping if necessary."""

        if not self._bucket:
            return
        wait_time = self._bucket.consume(tokens)
        if wait_time > 0:
            logger.debug("Rate limiter sleeping for %.3fs", wait_time)
            self._sleeper(wait_time)


class CircuitBreaker:
    """Circuit breaker implementation with half-open recovery."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_time: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        self._failure_threshold = failure_threshold
        self._recovery_time = max(0.0, recovery_time)
        self._clock = clock
        self._state = "closed"
        self._failure_count = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> str:
        return self._state

    def allow(self) -> None:
        """Ensure the circuit allows a new call."""

        if self._state == "open":
            assert self._opened_at is not None
            now = self._clock()
            if self._recovery_time == 0 or now - self._opened_at >= self._recovery_time:
                logger.debug("Circuit breaker moving to half-open state")
                self._state = "half_open"
            else:
                raise CircuitOpenError("Circuit is open")

    def record_success(self) -> None:
        """Record a successful call."""

        self._failure_count = 0
        self._state = "closed"
        self._opened_at = None

    def record_failure(self) -> None:
        """Record a failed call and open the circuit if needed."""

        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            if self._state != "open":
                logger.warning("Circuit breaker opened after %s failures", self._failure_count)
            self._state = "open"
            self._opened_at = self._clock()
        else:
            self._state = "closed"

    def force_open(self) -> None:
        """Force the circuit into an open state."""

        self._state = "open"
        self._opened_at = self._clock()

    def reset(self) -> None:
        """Reset the circuit back to a closed state."""

        self._failure_count = 0
        self._state = "closed"
        self._opened_at = None
