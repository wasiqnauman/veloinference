"""Batch scheduling policies."""

from __future__ import annotations

from time import monotonic

from gateway.core.models import PendingRequest


def remaining_wait_time(
    first_request: PendingRequest,
    max_wait_ms: int,
) -> float:
    elapsed = monotonic() - first_request.metadata.enqueued_at
    max_wait_seconds = max_wait_ms / 1000
    return max(0.0, max_wait_seconds - elapsed)


def request_has_expired(request: PendingRequest) -> bool:
    deadline_ms = request.metadata.deadline_ms
    if deadline_ms is None:
        return False

    elapsed_ms = (monotonic() - request.metadata.enqueued_at) * 1000
    return elapsed_ms >= deadline_ms
