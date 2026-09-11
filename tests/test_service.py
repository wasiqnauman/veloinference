"""Inference service mode tests."""

import pytest

from gateway.backends.base import InferenceBackend
from gateway.core.batcher import DynamicBatcher
from gateway.core.models import BackendOutput, InferenceRequest, PendingRequest
from gateway.core.service import InferenceService


class _Backend(InferenceBackend):
    async def infer_batch(
        self,
        requests: list[PendingRequest],
    ) -> list[BackendOutput]:
        return [
            BackendOutput(output_text=request.payload.input_text)
            for request in requests
        ]


class _Clock:
    def __init__(self) -> None:
        self.now = 10.0

    def monotonic(self) -> float:
        return self.now


@pytest.mark.asyncio
async def test_pass_through_adds_normalized_response_metadata() -> None:
    backend = _Backend()
    clock = _Clock()
    batcher = DynamicBatcher(
        backend=backend,
        max_batch_size=1,
        max_wait_ms=0,
        queue_max_size=1,
        clock=clock,
    )
    service = InferenceService(backend, batcher, "pass_through", clock)

    response = await service.infer(InferenceRequest(input_text="hello"))

    assert response.output_text == "hello"
    assert response.batch_size == 1
    assert response.batch_id is None
    assert response.queue_ms == 0
    assert response.deadline_met is None
