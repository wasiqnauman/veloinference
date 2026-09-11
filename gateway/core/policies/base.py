"""Pure policy contracts for deciding when a batch should close."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

DispatchReason = Literal[
    "batch_full",
    "wait_window_elapsed",
    "deadline_slack_exhausted",
    "low_load_bypass",
    "estimated_fill",
    "configured_wait",
]


@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    """Immutable facts a policy may use for one scheduling decision."""

    now: float
    oldest_enqueued_at: float
    compatible_queue_size: int
    max_batch_size: int
    max_wait_s: float
    arrival_rate_per_s: float
    estimated_backend_s: float
    earliest_deadline_at: float | None


@dataclass(frozen=True, slots=True)
class DispatchDecision:
    """A pure policy result; sleeping and I/O belong to the batcher."""

    dispatch_now: bool
    wait_s: float
    reason: DispatchReason


class BatchPolicy(Protocol):
    """Protocol implemented by fixed and adaptive batch-closing policies."""

    def decide(self, snapshot: QueueSnapshot) -> DispatchDecision:
        """Return a deterministic decision without sleeping or performing I/O."""
