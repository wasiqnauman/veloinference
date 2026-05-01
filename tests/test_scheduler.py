"""Scheduler tests."""

from time import monotonic

from gateway.core.models import BatchMetadata, InferenceRequest, PendingRequest
from gateway.core.scheduler import remaining_wait_time


def test_remaining_wait_time_is_bounded() -> None:
    request = PendingRequest(
        metadata=BatchMetadata(
            request_id="req-1",
            model="mock",
            enqueued_at=monotonic(),
            deadline_ms=None,
        ),
        payload=InferenceRequest(input_text="hello"),
        future=None,
    )

    timeout = remaining_wait_time(request, max_wait_ms=10)

    assert 0 <= timeout <= 0.01
