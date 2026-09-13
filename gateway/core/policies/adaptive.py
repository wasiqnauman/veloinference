"""Small deterministic adaptive batch-closing policy."""

from __future__ import annotations

from gateway.core.policies.base import DispatchDecision, QueueSnapshot


class AdaptiveWindowPolicy:
    """Close batches using queue age, arrival rate, backend time, and deadlines."""

    def __init__(self, low_load_threshold: float = 1.0) -> None:
        if low_load_threshold < 0:
            raise ValueError("low_load_threshold must be nonnegative")
        self._low_load_threshold = low_load_threshold

    def decide(self, snapshot: QueueSnapshot) -> DispatchDecision:
        """Return one deterministic dispatch or wait decision."""
        if snapshot.compatible_queue_size >= snapshot.max_batch_size:
            return DispatchDecision(True, 0.0, "batch_full")

        oldest_age = max(0.0, snapshot.now - snapshot.oldest_enqueued_at)
        remaining_window = max(0.0, snapshot.max_wait_s - oldest_age)
        if remaining_window <= 0.0:
            return DispatchDecision(True, 0.0, "wait_window_elapsed")

        deadline_budget = None
        if snapshot.earliest_deadline_at is not None:
            deadline_budget = (
                snapshot.earliest_deadline_at
                - snapshot.now
                - snapshot.estimated_backend_s
            )
            if deadline_budget <= 0.0:
                return DispatchDecision(True, 0.0, "deadline_slack_exhausted")

        if snapshot.arrival_rate_per_s <= 0.0:
            return DispatchDecision(True, 0.0, "low_load_bypass")

        expected_companions = snapshot.arrival_rate_per_s * remaining_window
        if expected_companions < self._low_load_threshold:
            return DispatchDecision(True, 0.0, "low_load_bypass")

        fill_eta = (
            snapshot.max_batch_size - snapshot.compatible_queue_size
        ) / snapshot.arrival_rate_per_s
        wait_s = min(remaining_window, fill_eta)
        if deadline_budget is not None:
            wait_s = min(wait_s, deadline_budget)
        reason = "estimated_fill" if fill_eta < remaining_window else "configured_wait"
        return DispatchDecision(False, max(0.0, wait_s), reason)
