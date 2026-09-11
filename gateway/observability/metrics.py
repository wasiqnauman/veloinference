"""Small in-process counters and EWMAs for scheduling diagnostics."""

from __future__ import annotations

from dataclasses import dataclass

from gateway.core.models import BatchKey


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    """Immutable metrics view suitable for diagnostics and tests."""

    received_requests: int
    completed_requests: int
    failed_requests: int
    rejected_requests: int
    batches: int
    batch_sizes: tuple[int, ...]
    backend_latency_ewma_s: float | None
    arrival_rate_ewma_per_s: dict[str, float]


class MetricsRegistry:
    """Track only measurements needed by the gateway and adaptive policy."""

    def __init__(self, ewma_alpha: float = 0.2) -> None:
        if not 0 < ewma_alpha <= 1:
            raise ValueError("ewma_alpha must be in (0, 1]")
        self._alpha = ewma_alpha
        self._received_requests = 0
        self._completed_requests = 0
        self._failed_requests = 0
        self._rejected_requests = 0
        self._batches = 0
        self._batch_sizes: list[int] = []
        self._backend_latency_ewma_s: float | None = None
        self._arrival_rate_ewma_per_s: dict[BatchKey, float] = {}
        self._last_arrival_at: dict[BatchKey, float] = {}

    def record_received(self, key: BatchKey, received_at: float) -> None:
        """Record one accepted request and update its arrival-rate EWMA."""
        self._received_requests += 1
        previous = self._last_arrival_at.get(key)
        if previous is not None and received_at > previous:
            rate = 1.0 / (received_at - previous)
            self._arrival_rate_ewma_per_s[key] = self._ewma(
                self._arrival_rate_ewma_per_s.get(key), rate
            )
        self._last_arrival_at[key] = received_at

    def record_completed(self) -> None:
        """Record one successful request."""
        self._completed_requests += 1

    def record_failed(self) -> None:
        """Record one request that reached a backend failure."""
        self._failed_requests += 1

    def record_rejected(self) -> None:
        """Record one request rejected before it entered a queue."""
        self._rejected_requests += 1

    def record_batch(self, batch_size: int) -> None:
        """Record one dispatch and its observed size."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self._batches += 1
        self._batch_sizes.append(batch_size)

    def record_backend_latency(self, latency_s: float) -> None:
        """Update the global backend-latency EWMA."""
        if latency_s < 0:
            raise ValueError("latency_s must be nonnegative")
        self._backend_latency_ewma_s = self._ewma(
            self._backend_latency_ewma_s,
            latency_s,
        )

    def arrival_rate_per_s(self, key: BatchKey) -> float:
        """Return the current arrival-rate estimate for one compatibility key."""
        return self._arrival_rate_ewma_per_s.get(key, 0.0)

    def backend_latency_s(self) -> float:
        """Return the current latency estimate or zero before observations."""
        return self._backend_latency_ewma_s or 0.0

    def snapshot(self) -> MetricsSnapshot:
        """Return an immutable copy of all tracked measurements."""
        arrival_rates = {
            self._key_label(key): rate
            for key, rate in self._arrival_rate_ewma_per_s.items()
        }
        return MetricsSnapshot(
            received_requests=self._received_requests,
            completed_requests=self._completed_requests,
            failed_requests=self._failed_requests,
            rejected_requests=self._rejected_requests,
            batches=self._batches,
            batch_sizes=tuple(self._batch_sizes),
            backend_latency_ewma_s=self._backend_latency_ewma_s,
            arrival_rate_ewma_per_s=arrival_rates,
        )

    def _ewma(self, previous: float | None, value: float) -> float:
        if previous is None:
            return value
        return self._alpha * value + (1 - self._alpha) * previous

    @staticmethod
    def _key_label(key: BatchKey) -> str:
        return f"{key.model}|{key.max_tokens}|{key.temperature}"
