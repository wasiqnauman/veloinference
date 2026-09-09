"""Fixed maximum-size/maximum-wait batching policy."""

from gateway.core.policies.base import DispatchDecision, QueueSnapshot


class FixedWindowPolicy:
    """Close a batch at its size limit, wait limit, or deadline slack limit."""

    def decide(self, snapshot: QueueSnapshot) -> DispatchDecision:
        """Return the fixed-window decision for an immutable queue snapshot."""
        if snapshot.compatible_queue_size >= snapshot.max_batch_size:
            return DispatchDecision(True, 0.0, "batch_full")

        oldest_age = max(0.0, snapshot.now - snapshot.oldest_enqueued_at)
        remaining_window = max(0.0, snapshot.max_wait_s - oldest_age)
        if remaining_window <= 0.0:
            return DispatchDecision(True, 0.0, "wait_window_elapsed")

        if snapshot.earliest_deadline_at is not None:
            service_slack = (
                snapshot.earliest_deadline_at
                - snapshot.now
                - snapshot.estimated_backend_s
            )
            if service_slack <= remaining_window:
                return DispatchDecision(True, 0.0, "deadline_slack_exhausted")

        return DispatchDecision(False, remaining_window, "configured_wait")
